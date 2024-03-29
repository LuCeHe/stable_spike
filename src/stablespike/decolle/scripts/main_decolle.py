#!/bin/python
# -----------------------------------------------------------------------------
# File Name : train_lenet_decolle
# Author: Emre Neftci
#
# Creation Date : Sept 2. 2019
# Last Modified :
#
# Copyright : (c) UC Regents, Emre Neftci
# Licence : GPLv2
# -----------------------------------------------------------------------------

import json, shutil, time, socket, os, argparse, copy
import numpy as np
import torch

from pyaromatics.stay_organized.utils import NumpyEncoder, str2val
from pyaromatics.torch_tools.esoteric_optimizers.adabelief import AdaBelief
from stablespike.decolle.decolle.base_model import LIFLayerPlus, frDECOLLELoss
from stablespike.decolle.torchneuromorphic.nmnist import nmnist_dataloaders
from stablespike.decolle.torchneuromorphic.dvs_gestures import dvsgestures_dataloaders
from stablespike.decolle.decolle.lenet_decolle_model import LenetDECOLLE, DECOLLELoss
from stablespike.decolle.decolle.utils import train, test, accuracy, save_checkpoint, \
    load_model_from_checkpoint, prepare_experiment, write_stats, cross_entropy_one_hot

CDIR = os.path.dirname(os.path.realpath(__file__))
DATADIR = os.path.abspath(os.path.join(CDIR, '..', '..', '..', 'data'))
np.set_printoptions(precision=4)


def main(args):
    stop_time = time.perf_counter() + args.stop_time - 30 * 60
    starting_epoch = 0
    early_stop = 12
    device = args.device if torch.cuda.is_available() else 'cpu'

    # get name of this file with code that is windows and linux compatible
    name = os.path.split(__file__)[1].split('.')[0]
    args.file_name = name
    results = {}

    params, writer, dirs = prepare_experiment(name=name, args=args)
    log_dir = dirs['log_dir']
    checkpoint_dir = dirs['checkpoint_dir']

    if 'test' in args.comments:
        params['Nhid'] = [50, 40]
        params['Mhid'] = [11]
        params['batch_size'] = 16
        params['num_layers'] = 3
        params['num_conv_layers'] = 2

    # print args with json
    args.__dict__.update(dirs)
    print(json.dumps(args.__dict__, indent=2))
    print(json.dumps(params, indent=2))
    results.update(params)

    if 'nmnist' in params['dataset']:
        dataset = nmnist_dataloaders
        create_data = dataset.create_dataloader
        root = os.path.join(DATADIR, 'nmnist', 'n_mnist.hdf5')
    else:
        dataset = dvsgestures_dataloaders
        create_data = dataset.create_dataloader
        root = os.path.join(DATADIR, 'dvsgesture', 'dvsgestures.hdf5')
        # root = os.path.join(DATADIR, 'dvs', 'dvsgestures')

    ## Load Data
    gen_train, gen_val, gen_test = create_data(
        root=root,
        chunk_size_train=params['chunk_size_train'],
        chunk_size_test=params['chunk_size_test'],
        batch_size=params['batch_size'],
        dt=params['deltat'],
        num_workers=params['num_dl_workers']
    )

    data_batch, target_batch = next(iter(gen_train))
    data_batch = torch.Tensor(data_batch).to(device)
    target_batch = torch.Tensor(target_batch).to(device)

    # d, t = next(iter(gen_train))
    input_shape = data_batch.shape[-3:]

    # Backward compatibility
    if 'dropout' not in params.keys():
        params['dropout'] = [.5]

    curve_name = str2val(args.comments, 'sgcurve', str, default='dfastsigmoid')
    continuous_sg = 'continuous' in args.comments
    normcurv = 'normcurv' in args.comments
    oningrad = 'oningrad' in args.comments
    forwback = 'forwback' in args.comments
    sgoutn = 'sgoutn' in args.comments

    sg_kwargs = {
        'curve_name': curve_name, 'continuous': continuous_sg, 'normalized_curve': normcurv,
        'on_ingrad': oningrad, 'forwback': forwback, 'sgoutn': sgoutn
    }
    if 'condIV' in args.comments:
        print('Using condition IV')
        sg_kwargs.update({'rule': 'IV'})
    elif 'condI_IV' in args.comments:
        print('Using condition I/IV')
        sg_kwargs.update({'rule': 'I_IV'})
    elif 'condI' in args.comments:
        print('Using condition I')
        sg_kwargs.update({'rule': 'I'})
    else:
        sg_kwargs.update({'rule': '0'})

    lif_layer_type = lambda *args, **kwargs: \
        LIFLayerPlus(*args, sg_kwargs=sg_kwargs, **kwargs)

    ## Create Model, Optimizer and Loss
    net = LenetDECOLLE(out_channels=params['out_channels'],
                       Nhid=params['Nhid'],
                       Mhid=params['Mhid'],
                       kernel_size=params['kernel_size'],
                       pool_size=params['pool_size'],
                       input_shape=params['input_shape'],
                       alpha=params['alpha'],
                       alpharp=params['alpharp'],
                       dropout=params['dropout'],
                       beta=params['beta'],
                       num_conv_layers=params['num_conv_layers'],
                       num_mlp_layers=params['num_mlp_layers'],
                       lc_ampl=params['lc_ampl'],
                       lif_layer_type=lif_layer_type,
                       method=params['learning_method'],
                       with_output_layer=params['with_output_layer']).to(device)

    if 'adabelief' in args.comments:
        opt_fn = AdaBelief
    else:
        opt_fn = torch.optim.Adamax
    lr = str2val(args.comments, 'lr', float, default=params['learning_rate'])
    print('Learning rate = {}'.format(lr))

    if hasattr(params['learning_rate'], '__len__'):
        from stablespike.decolle.decolle.utils import MultiOpt

        opts = []
        for i in range(len(lr)):
            opts.append(
                opt_fn(net.get_trainable_parameters(i), lr=lr[i],
                       betas=params['betas']))
        opt = MultiOpt(*opts)
    else:
        opt = opt_fn(net.get_trainable_parameters(), lr=lr, betas=params['betas'])

    reg_l = params['reg_l'] if 'reg_l' in params else None

    print('reg', params['loss_scope'], reg_l)
    if 'loss_scope' in params and params['loss_scope'] == 'global':
        loss = [None for _ in range(len(net))]
        if net.with_output_layer:
            loss[-1] = cross_entropy_one_hot
        else:
            raise RuntimeError('bptt mode needs output layer')
    elif 'allxe' in args.comments:
        loss = [cross_entropy_one_hot for _ in range(len(net))]
    else:
        loss = [torch.nn.SmoothL1Loss() for _ in range(len(net))]
        if net.with_output_layer:
            loss[-1] = cross_entropy_one_hot

    decolle_loss = DECOLLELoss(net=net, loss_fn=loss, reg_l=reg_l)
    if 'frcontrol' in args.comments:
        frfrom = str2val(args.comments, 'frfrom', float, default=None)
        frto = str2val(args.comments, 'frto', float, default=None)
        switchep = str2val(args.comments, 'switchep', int, default=5)
        lmbd = str2val(args.comments, 'lmbd', float, default=.1)
        onlyreg = 'onlyreg' in args.comments
        decolle_loss = frDECOLLELoss(net=net, loss_fn=loss, frfrom=frfrom, frto=frto, switchep=switchep, lmbd=lmbd,
                                     onlyreg=onlyreg)

    ##Initialize
    net.init_parameters(data_batch[:32])

    if not 'test' in args.comments:
        from stablespike.decolle.decolle.init_functions import init_LSUV
        init_LSUV(net, data_batch[:32])

    ##Resume if necessary
    if args.resume_from is not None:
        print("Checkpoint directory " + checkpoint_dir)
        if not os.path.exists(checkpoint_dir) and not args.no_save:
            os.makedirs(checkpoint_dir)
        starting_epoch = load_model_from_checkpoint(checkpoint_dir, net, opt)
        print('Learning rate = {}. Resumed from checkpoint'.format(opt.param_groups[-1]['lr']))

    # Printing parameters
    if args.verbose:
        print('Using the following parameters:')
        m = max(len(x) for x in params)
        for k, v in zip(params.keys(), params.values()):
            print('{}{} : {}'.format(k, ' ' * (m - len(k)), v))

    print('\n------Starting training with {} DECOLLE layers-------'.format(len(net)))

    best_net = copy.deepcopy(net)
    activities = []
    val_activities = []
    # --------TRAINING LOOP----------
    if not args.no_train:
        train_losses = []
        val_losses = []
        val_accs = []
        bad_test_acc = []
        val_acc_hist = []
        best_loss = np.inf
        best_loss_epoch = -1
        best_acc = 0
        best_acc_epoch = -1

        epochs = params['num_epochs'] if not 'test' in args.comments else 2
        for e in range(starting_epoch, epochs):

            interval = e // params['lr_drop_interval']
            lr = opt.param_groups[-1]['lr']
            if interval > 0:
                print('Changing learning rate from {} to {}'.format(lr, opt.param_groups[-1]['lr']))
                opt.param_groups[-1]['lr'] = np.array(params['learning_rate']) / (interval * params['lr_drop_factor'])
            else:
                print('Changing learning rate from {} to {}'.format(lr, opt.param_groups[-1]['lr']))
                opt.param_groups[-1]['lr'] = np.array(params['learning_rate'])

            print('---------------Epoch {}-------------'.format(e))
            if not args.no_save:
                print('---------Saving checkpoint---------')
                save_checkpoint(e, checkpoint_dir, net, opt)

            val_loss, val_acc, val_act_rate = test(gen_val, decolle_loss, net, params['burnin_steps'], print_error=True,
                                                   shorten='test' in args.comments, epoch=e)
            val_acc_hist.append(val_acc)
            val_losses.append(val_loss)
            val_accs.append(val_acc)

            if len(val_activities) == 0:  # suggest
                val_activities = [[] for _ in val_act_rate]

            for frs, fr in zip(val_activities, val_act_rate):
                frs.append(fr)

            _, bad_tacc, _ = test(gen_test, decolle_loss, net, params['burnin_steps'], print_error=True,
                                  shorten='test' in args.comments, epoch=e)
            bad_test_acc.append(bad_tacc)

            if min(val_loss) < best_loss:
                best_loss = min(val_loss)
                best_loss_epoch = e

            if max(val_acc) > best_acc:
                best_acc = max(val_acc)
                best_acc_epoch = e
                best_net = copy.deepcopy(net)

            if not args.no_save:
                write_stats(e, val_acc, val_loss, writer)
                np.save(log_dir + '/test_acc.npy', np.array(val_acc_hist), )

            total_loss, act_rate = train(gen_train, decolle_loss, net, opt, e, params['burnin_steps'],
                                         online_update=params['online_update'], shorten='test' in args.comments)
            train_losses.append(total_loss)

            if len(activities) == 0:  # suggest
                activities = [[] for _ in act_rate]

            for frs, fr in zip(activities, act_rate):
                frs.append(fr)

            if not args.no_save:
                for i in range(len(net)):
                    writer.add_scalar('/act_rate/{0}'.format(i), act_rate[i], e)

            results.update(train_losses=train_losses, val_loss=val_losses, val_acc=val_accs, bad_test_acc=bad_test_acc)
            if time.perf_counter() > stop_time:
                print('Time assigned to this job is over, stopping')
                break

            if e - best_loss_epoch > early_stop and e - best_acc_epoch > early_stop:
                print('Early stopping')
                break

    test_loss, test_acc, _ = test(gen_test, decolle_loss, best_net, params['burnin_steps'], print_error=True,
                                  shorten='test' in args.comments)
    results.update(test_loss=test_loss, test_acc=test_acc)

    for i, act in enumerate(activities):
        results[f'fr_{i}'] = act

    for i, act in enumerate(val_activities):
        results[f'val_fr_{i}'] = act

    return args, results


def parse_args():
    PPATH = os.path.abspath(os.path.join(CDIR, '..', 'scripts', 'parameters'))
    params_dvs = os.path.join(PPATH, 'params_dvsgestures_torchneuromorphic.yml')
    params_nmnist = os.path.join(PPATH, 'params_nmnist.yml')

    parser = argparse.ArgumentParser(description='DECOLLE for event-driven object recognition')
    parser.add_argument('--device', type=str, default='cuda', help='Device to use (cpu or cuda)')
    parser.add_argument('--resume_from', type=str, default=None, metavar='path_to_logdir',
                        help='Path to a previously saved checkpoint')
    parser.add_argument('--params_file', type=str, default='',
                        help='Path to parameters file to load. Ignored if resuming from checkpoint')
    parser.add_argument('--no_save', dest='no_save', action='store_false',
                        help=r'Set this flag if you don\'t want to save results')
    parser.add_argument('--save_dir', type=str, default='default', help='Name of subdirectory to save results in')
    parser.add_argument('--verbose', type=bool, default=False, help='print verbose outputs')
    parser.add_argument('--seed', type=int, default=-1, help='CPU and GPU seed')
    parser.add_argument('--no_train', dest='no_train', action='store_true', help='Train model (useful for resume)')
    parser.add_argument('--comments', type=str, default='test_frcontrol_frfrom:.5_allxe',
                        help='String to activate extra behaviors')
    # parser.add_argument('--comments', type=str, default='test', help='String to activate extra behaviors')
    parser.add_argument("--stop_time", default=6000, type=int, help="Stop time (seconds)")
    parser.add_argument('--datasetname', type=str, default='nmnist', help='Dataset to use', choices=['dvs', 'nmnist'])

    parsed, unknown = parser.parse_known_args()

    for arg in unknown:
        if arg.startswith(("-", "--")):
            # you can pass any arguments to add_argument
            parser.add_argument(arg, type=str)

    args = parser.parse_args()

    if args.datasetname == 'dvs':
        args.params_file = params_dvs
    else:
        args.params_file = params_nmnist

    return args


if __name__ == '__main__':
    args = parse_args()

    time_start = time.perf_counter()
    args, results = main(args)
    time_elapsed = (time.perf_counter() - time_start)

    results.update(time_elapsed=time_elapsed)
    results.update(hostname=socket.gethostname())

    if not args.no_save:
        # remove events files
        events = [e for e in os.listdir(args.log_dir) if 'events' in e]
        for e in events:
            if os.path.exists(os.path.join(args.log_dir, e)):
                os.remove(os.path.join(args.log_dir, e))

                # remove checkpoints folder
    if os.path.exists(os.path.join(args.log_dir, 'checkpoints')):
        shutil.rmtree(os.path.join(args.log_dir, 'checkpoints'))

    args_dict = args.__dict__
    for d in [args_dict, results]:
        string_result = json.dumps(d, indent=4, cls=NumpyEncoder)
        var_name = [k for k, v in locals().items() if v is d if not k == 'd'][0]
        print(var_name)
        # print(d.name)
        print(string_result)

        path = os.path.join(args.log_dir, var_name + '.txt')
        with open(path, "w") as f:
            f.write(string_result)

    shutil.make_archive(args.log_dir, 'zip', args.log_dir)
    print('All done, in ' + str(time_elapsed) + 's')
