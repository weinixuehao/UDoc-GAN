import os

# os.environ["CUDA_VISIBLE_DEVICES"] = "1"
# os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"

import torch
import torch.nn as nn
import argparse
from tool.model import LPNet
from tool.dataset import LPNet_Dataset
from tool.scheduler import GradualWarmupScheduler
from tool.utils import *
from tqdm import tqdm

parser = argparse.ArgumentParser(description='')
parser.add_argument('--epochs',     default=200,    type=int, help='number of total epochs')
parser.add_argument('--batch_size', default=16,     type=int, help='number of samples in one batch')
parser.add_argument('--patch_size', default=256,    type=int, help='patch size')
parser.add_argument('--lr_init',    default=0.003,  type=float,  help='initial learning rate')
parser.add_argument('--lr_min',     default=0.0005, type=float,  help='initial learning rate')
parser.add_argument('--data_dir',   default='/data4/wangyh/doc/wyh/dataset', type=str,  help='directory storing the training data')
parser.add_argument('--ckpt_dir',   default='./ckpts/lpnet',   dest='ckpt_dir',help='directory for checkpoints')
parser.add_argument('--local_rank', default=0,  help='if use distributed mode, must use variable local_rank')
parser.add_argument('--model',      default="LPNet", help='decise which data to choose')
args = parser.parse_args()

def initDevice():
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    return device

def main():
    '''  initial distributed mode  '''
    # rank = initial_distributed()

    if not os.path.exists(args.ckpt_dir):
        os.makedirs(args.ckpt_dir)
    
    device = initDevice()
    '''  model  '''
    model = LPNet(in_channels=3, out_channels=3)
    model.to(device)
    # model = torch.nn.parallel.DistributedDataParallel(model, device_ids=[rank])
    # if rank==0:
    #     print("LPNet parameters: ", sum(param.numel() for param in model.parameters())/1e6)

    '''  datasets  '''
    train_dataset       = LPNet_Dataset(f"{args.data_dir}/doc_color_train", args.model, args.patch_size)
    eval_dataset       = LPNet_Dataset(f"{args.data_dir}/doc_color_val", args.model, args.patch_size)
    # train_sampler       = torch.utils.data.distributed.DistributedSampler(train_dataset)
    # train_batch_sampler = torch.utils.data.BatchSampler(train_sampler, batch_size=args.batch_size, drop_last=True)
    # train_loader        = torch.utils.data.DataLoader(dataset=train_dataset, batch_sampler=train_batch_sampler, num_workers=20, pin_memory=False)
    train_loader        = torch.utils.data.DataLoader(dataset=train_dataset, batch_size=args.batch_size, shuffle=True)
    eval_loader        = torch.utils.data.DataLoader(dataset=eval_dataset, batch_size=args.batch_size)
    # if rank==0:
    #     print('Number of training data: %d' % len(train_dataset))

    '''  optimizer loss scheduler  '''
    criterion = nn.L1Loss()
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr_init)
    warmup_epochs = 10
    scheduler_cosine = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, 100, eta_min=args.lr_min)
    scheduler = GradualWarmupScheduler(optimizer, multiplier=1, total_epoch=warmup_epochs, after_scheduler=scheduler_cosine)

    '''  start training!  '''
    start_epoch = 0
    best_loss = float("inf")
    for epoch in range(start_epoch, args.epochs):
        # if rank==0:
        #     print("epoch: %d lr: %.4f" % (epoch, optimizer.param_groups[0]["lr"]))
        # train_sampler.set_epoch(epoch)

        # train
        model.train()
        epoch_loss = 0
        for _, (file, img, color) in enumerate(tqdm(train_loader), 0):
            optimizer.zero_grad()
            img, color = img.to(device), color.to(device)
            Pred_color = model(img)
            loss = criterion(Pred_color, color)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()

        # evaluate
        eval_loss = 0
        model.eval()
        with torch.no_grad():
            for _, (file, img, color) in enumerate(tqdm(eval_loader), 0):
                img, color = img.to(device), color.to(device)
                Pred_color = model(img)
                loss = criterion(Pred_color, color)
                eval_loss += loss.item()

        # if rank==0:
        #     # log loss
        #     print("epoch:{} train loss:{}".format(epoch, epoch_loss))
        #     if best_loss>epoch_loss:
        #         best_loss=epoch_loss
        #         torch.save(model.state_dict(), os.path.join(args.ckpt_dir, 'best_LPNet.pth'))
        # log loss
        print("epoch:{} train loss:{} eval loss:{}".format(epoch, epoch_loss, eval_loss))
        if best_loss>epoch_loss:
            best_loss=epoch_loss
            torch.save(model.state_dict(), os.path.join(args.ckpt_dir, 'best_LPNet.pth'))
        '''  save  '''
        # if rank==0:
        #     torch.save(model.state_dict(), os.path.join(args.ckpt_dir, 'latest_LPNet.pth'.format(epoch)))
        if epoch == 0:
            torch.save(model.state_dict(), os.path.join(args.ckpt_dir, 'latest_LPNet.pth'.format(epoch)))
        scheduler.step()


if __name__ == '__main__':
    init_seeds(1234)
    main()