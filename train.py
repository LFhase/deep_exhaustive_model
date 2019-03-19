# coding: utf-8
# created by deng on 2019-02-13

import torch
import json
import torch.nn.functional as F
from torch.utils.data import DataLoader

from utils.path_util import from_project_root, exists
from utils.torch_util import set_random_seed, get_device
from prepare_data import gen_vocab_from_data
from dataset import ExhaustiveDataset
from model import ExhaustiveModel
from eval import evaluate

N_TAGS = 7
TAG_WEIGHTS = [1, 1, 1, 1, 1, 1, 0]

RANDOM_SEED = 233
set_random_seed(RANDOM_SEED)

EMBED_URL = from_project_root("data/embeddings.npy")
TRAIN_URL = from_project_root("data/genia.train.iob2")
DEV_URL = from_project_root("data/genia.dev.iob2")
TEST_URL = from_project_root("data/genia.test.iob2")


def train(n_epochs=30,
          embedding_url=EMBED_URL,
          char_feat_dim=50,
          freeze=False,
          train_url=TRAIN_URL,
          dev_url=DEV_URL,
          max_region=10,
          learning_rate=0.001,
          batch_size=100,
          early_stop=5,
          clip_norm=5,
          device='auto',
          eval_on_test=False
          ):
    """ Train deep exhaustive model, Sohrab et al. 2018 EMNLP

    Args:
        n_epochs: number of epochs
        embedding_url: url to pretrained embedding file, set as None to use random embedding
        char_feat_dim: size of character level feature
        freeze: whether to freeze embedding
        train_url: url to train data
        dev_url: url to dev data
        max_region: max entity region size
        learning_rate: learning rate
        batch_size: batch_size
        early_stop: early stop for training
        clip_norm: whether to perform norm clipping, set to 0 if not need
        device: device for torch
        eval_on_test: whether to do evaluating on test set on every epoch
    """

    # print arguments
    arguments = json.dumps(vars(), indent=2)
    print("exhaustive model is training with arguments", arguments)
    device = get_device(device)

    train_set = ExhaustiveDataset(train_url, device=device, max_region=max_region)
    train_loader = DataLoader(train_set, batch_size=batch_size, drop_last=True,
                              collate_fn=train_set.collate_func)

    model = ExhaustiveModel(
        hidden_size=200,
        n_tags=7,
        char_feat_dim=char_feat_dim,
        embedding_url=embedding_url,
        bidirectional=True,
        max_region=max_region,
        n_embeddings=200000,
        embedding_dim=200,
        freeze=freeze
    )

    if device.type == 'cuda':
        print("using gpu,", torch.cuda.device_count(), "gpu(s) available!\n")
        # model = nn.DataParallel(model)
    else:
        print("using cpu\n")
    model = model.to(device)

    criterion = F.cross_entropy
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)

    max_f1, max_f1_epoch, cnt = 0, 0, 0
    tag_weights = torch.Tensor(TAG_WEIGHTS).to(device)

    # train and evaluate model
    for epoch in range(n_epochs):
        # switch to train mode
        model.train()
        batch_id = 0
        for data, labels in train_loader:
            optimizer.zero_grad()
            outputs = model.forward(*data)
            # use weight parameter to skip padding part
            loss = criterion(outputs, labels, weight=tag_weights)
            loss.backward()
            # gradient clipping
            if clip_norm > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=clip_norm)
            optimizer.step()
            if batch_id % 10 == 0:
                print("epoch #%d, batch #%d, loss: %.12f" % (epoch, batch_id, loss.item()))
            batch_id += 1

        cnt += 1
        # metrics on develop set
        dev_metrics = evaluate(model, dev_url)
        if dev_metrics['f1'] > max_f1:
            max_f1 = dev_metrics['f1']
            max_f1_epoch = epoch
            torch.save(model, from_project_root("data/model/exhaustive_model_epoch%d_%f.pt" % (epoch, max_f1)))
            cnt = 0

        # metrics on test set
        if eval_on_test:
            evaluate(model, TEST_URL)

        print("maximum of f1 value: %.6f, in epoch #%d\n" % (max_f1, max_f1_epoch))
        if cnt >= early_stop > 0:
            break

    print(arguments)


def main():
    if EMBED_URL and not exists(EMBED_URL):
        pretrained_url = from_project_root("data/PubMed-shuffle-win-30.bin")
        gen_vocab_from_data(TRAIN_URL, pretrained_url)
    train(eval_on_test=True)
    pass


if __name__ == '__main__':
    main()
