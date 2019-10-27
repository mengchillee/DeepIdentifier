from __future__ import print_function

import torch
import torch.nn as nn
import torch.optim as optim
import torch.utils.data as Data

import os
import argparse
from sklearn.metrics import classification_report

from deepidentifier import *
from utils import *

os.environ["CUDA_VISIBLE_DEVICES"] = "6, 7"

parser = argparse.ArgumentParser(description='')
parser.add_argument('--lr', default=0.001, type=float, help='learning rate')
parser.add_argument('--ep', default=5, type=int, help='total epochs')
parser.add_argument('--bs', default=256, type=int, help='batch size')
parser.add_argument('--al', default=0.1, type=int, help='alpha value')
parser.add_argument('--dp', default="../DMAL/waist_data", type=str, help='data path')
parser.add_argument('--resume', '-r', action='store_true', help='resume from checkpoint')
args = parser.parse_args()

print('==> Prepare data...')
ori_train_data, ori_test_data, ori_train_act, ori_test_act = read_dmal_act_data(args.dp)

all_ey = np.array([])
all_ep = np.array([])

right_sub_num = 0
fake_sub_num = 1

train_data, train_label = produce_data_label(ori_train_data[right_sub_num],
                                             np.delete(ori_train_data, [right_sub_num, fake_sub_num]),
                                             down=8)
test_data, test_label = produce_data_label(ori_test_data[right_sub_num],
                                           [ori_test_data[fake_sub_num]],
                                           down=1)

train_dataset = Data.TensorDataset(torch.FloatTensor(reshape_data(train_data)),
                                   torch.LongTensor(train_label))
train_loader = Data.DataLoader(
    dataset=train_dataset,
    batch_size=args.bs,
    shuffle=True,
    num_workers=8
)
test_dataset = Data.TensorDataset(torch.FloatTensor(reshape_data(test_data)),
                                  torch.LongTensor(test_label))
test_loader = Data.DataLoader(
    dataset=test_dataset,
    batch_size=args.bs,
    shuffle=False,
    num_workers=8
)

print('==> Build model...')
net = DeepIdentifier()
net = nn.DataParallel(net, device_ids=range(torch.cuda.device_count())).cuda()

ce = nn.CrossEntropyLoss()
mse = nn.MSELoss()
optimizer = optim.Adam(net.parameters(), lr=args.lr)

def train(epoch):
    net.train()
    train_loss, correct, total = 0, 0, 0

    for batch_idx, (train_bx, train_by, _) in enumerate(train_loader):
        train_bx, train_by = train_bx.cuda(), train_by.cuda()

        outputs1, outputs2 = net(train_bx)
        batch_loss = ce(outputs1, train_by) + mse(outputs2, train_bx) * args.al

        optimizer.zero_grad()
        batch_loss.backward()
        optimizer.step()

        train_loss += batch_loss.data
        _, predicted = torch.max(outputs1.data, 1)
        total += train_by.size(0)
        correct += predicted.eq(train_by.data).cpu().sum()

        progress_bar(batch_idx, len(train_loader), 'Loss: %.3f | Acc: %.3f (%d/%d)'
            % (train_loss/(batch_idx+1), float(correct)/total, correct, total))

def test(epoch):
    net.eval()
    test_loss, correct, total = 0, 0, 0
    true_cul, pred_cul = np.array([]), np.array([])

    for batch_idx, (test_bx, test_by, _) in enumerate(test_loader):
        with torch.no_grad():
            test_bx, test_by = test_bx.cuda(), test_by.cuda()

            outputs1, outputs2 = net(test_bx)
            batch_loss = ce(outputs1, test_by) + mse(outputs2, test_bx) * args.al

            test_loss += batch_loss.data
            _, predicted = torch.max(outputs1.data, 1)
            total += test_by.size(0)
            correct += predicted.eq(test_by.data).cpu().sum()

            true_cul = np.concatenate((true_cul, test_by.data.cpu().numpy()), axis=0)
            pred_cul = np.concatenate((pred_cul, predicted.data.cpu().numpy()), axis=0)

            progress_bar(batch_idx, len(test_loader), 'Loss: %.3f | Acc: %.3f (%d/%d)'
                % (test_loss/(batch_idx+1), float(correct)/total, correct, total))

    return true_cul, pred_cul

for epoch in range(args.ep):
    print('Epoch %d' % epoch)
    train(epoch)
    ey, ep = test(epoch)
    print('\n')
    if epoch in range(args.ep)[-5:]:
        all_ey = np.concatenate((all_ey, ey), axis=0)
        all_ep = np.concatenate((all_ep, ep), axis=0)

print(classification_report(all_ey, all_ep))