# # Train a deep, recurrent convolutional SNN on the SHD dataset
#
# In this notebook, we demonstrate the training of a 3-layer convolutional SNN
# with recurrent connections in each hidden layer on the
# [SHD dataset](https://zenkelab.org/resources/spiking-heidelberg-datasets-shd/).
#
# We will introduce the use of the `layer` module to initialize feed-forward
# and recurrent connections at the same time, from the same target parameter $\sigma_U$.

# First, imports
import os, socket, json, shutil, time, argparse, string, random, gc

import numpy as np
import torch

import matplotlib.pyplot as plt
import seaborn as sns
from torch.nn import init

from pyaromatics.stay_organized.utils import NumpyEncoder, str2val
from pyaromatics.torch_tools.esoteric_optimizers.adabelief import AdaBelief
from stablespike.fluctuations.examples.fluctuation_dataloaders import datasets_available, load_dataset
from stablespike.fluctuations.examples.fluctuation_default_config import default_config

from stablespike.fluctuations.stork.models import RecurrentSpikingModel
from stablespike.fluctuations.stork.nodes import InputGroup, ReadoutGroup, LIFGroup, MaxPool2d
from stablespike.fluctuations.stork.connections import Connection, Conv2dConnection, ConvConnection
from stablespike.fluctuations.stork.generators import StandardGenerator
from stablespike.fluctuations.stork.initializers import FluctuationDrivenCenteredNormalInitializer, DistInitializer, \
    FluctuationDrivenNormalInitializer
from stablespike.fluctuations.stork.layers import ConvLayer

import stablespike.fluctuations.stork as stork
from pyaromatics.torch_tools.esotorch_layers.torch_sgs import ConditionedSG

FILENAME = os.path.realpath(__file__)
CDIR = os.path.dirname(FILENAME)


def main(args):
    print(json.dumps(args.__dict__, indent=4, cls=NumpyEncoder))

    # ## Load Dataset
    stop_time = time.perf_counter() + args.stop_time - 30 * 60

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    ## Load Dataset
    dataset = load_dataset(args.dataset)
    train_dataset, valid_dataset, test_dataset = dataset['train'], dataset['valid'], dataset['test']
    dconfig = dataset['data_config']
    dt = dconfig['dt']
    duration = dconfig['duration']
    if 'cifar10' in args.dataset and 'deep' in args.comments:
        duration = 0.3
    nb_time_steps = dconfig['nb_time_steps']
    nb_inputs = dconfig['nb_inputs']
    input_shape = dconfig['input_shape']

    # ## Set up the model
    # Model Parameters
    # # # # # # # # # # #

    deep = 'deep' in args.comments
    config = default_config(args.dataset, deep=deep)
    beta = config['beta']
    nb_conv_blocks = config['nb_conv_blocks']
    nb_hidden_layers = config['nb_hidden_layers']
    nb_classes = config['nb_classes']
    nb_filters = config['nb_filters']
    kernel_size = config['kernel_size']
    stride = config['stride']
    padding = config['padding']
    recurrent_kwargs = config['recurrent_kwargs']
    maxpool_kernel_size = config['maxpool_kernel_size']
    dropout_p = config['dropout_p']
    lr = str2val(args.comments, 'lr', float, default=config['lr'])

    # Neuron Parameters
    # # # # # # # # # # #

    neuron_group = LIFGroup
    tau_readout = duration

    # Training parameters
    # # # # # # # # # # #

    batch_size = config['batch_size'] if torch.cuda.is_available() else 2
    batch_size = batch_size if not 'test' in args.comments else 2
    device = torch.device("cuda") if torch.cuda.is_available() else 'cpu'
    dtype = torch.float
    nb_epochs = config['epochs'] if args.epochs < 0 else args.epochs

    # #### SuperSpike and loss function setup
    act_fn = stork.activations.SuperSpike
    act_fn.beta = beta

    if 'test' in args.comments:
        nb_conv_blocks = 3
        nb_hidden_layers = 2
        nb_filters = 10
        kernel_size = 2
        stride = 1
        padding = 0
        recurrent_kwargs = dict()

        batch_size = 12

    loss_stack = stork.loss_stacks.MaxOverTimeCrossEntropy()

    # #### Optimizer setup
    if 'adabelief' in args.comments:
        print('Using AdaBelief')
        opt = AdaBelief
    else:
        opt = stork.optimizers.SMORMS3

    nb_workers = 4 if not 'DESKTOP' in socket.gethostname() else 0
    persistent_workers = not 'DESKTOP' in socket.gethostname()
    generator = StandardGenerator(nb_workers=nb_workers, persistent_workers=persistent_workers)

    # #### Regularizer setup
    # Define regularizer parameters (set regularizer strenght to 0 if you don't want to use them)
    upperBoundL2Strength = 0.01 if not 'noreg' in args.comments else 0.0
    # Regularizes spikecount: 7 spikes ~ 10 Hz in 700ms simulation time
    upperBoundL2Threshold = config['upperBoundL2Threshold']

    # Define regularizer list
    regs = []
    reg_kwargs = {
        'strength': upperBoundL2Strength,
        'threshold': upperBoundL2Threshold,
        'dims': [-2, -1],
    }
    if 'regp5' in args.comments:
        thr = str2val(args.comments, 'regp5', float, default=0.5)
        reg_kwargs.update({'sum_or_mean': 'mean', 'threshold': thr})


    if 'reglag' in args.comments:
        if args.dataset == 'cifar10':
            reglag = 10
        else:
            reglag = 40
        reg_kwargs.update({'reglag': reglag})



    regUB = stork.regularizers.UpperBoundL2(**reg_kwargs)
    regs.append(regUB)

    # #### Initializer setup
    # We initialize in the fluctuation-driven regime with a target membrane potential standard deviation $\sigma_U=1.0$.
    # Additionally, we set the proportion of membrane potential fluctuations driven by feed-forward inputs to $\alpha=0.9$.
    sigma_u = 1.0
    nu = config['nu']

    if 'muchange' in args.comments:
        mu = str2val(args.comments, 'muchange', float, default=1.)
        nu = str2val(args.comments, 'nu', float, default=nu)
        epsilon = str2val(args.comments, 'eps', float, default=-1)

        initializer = FluctuationDrivenNormalInitializer(
            mu_u=mu,
            xi=1 / sigma_u,
            nu=nu,
            epsilon=epsilon,
            timestep=dt,
            alpha=.9
        )
    else:
        initializer = FluctuationDrivenCenteredNormalInitializer(
            sigma_u=sigma_u,
            nu=nu,
            timestep=dt,
            alpha=0.9
        )

    readout_initializer = DistInitializer(
        dist=torch.distributions.Normal(0, 1),
        scaling='1/sqrt(k)'
    )

    print('Assemble the model...')

    model = RecurrentSpikingModel(
        batch_size,
        nb_time_steps,
        nb_inputs,
        device,
        dtype
    )

    # INPUT LAYER
    # # # # # # # # # # # # # # #
    input_group = model.add_group(InputGroup(input_shape))

    # Set input group as upstream of first hidden layer
    upstream_group = input_group

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
        print('Using condition 0')
        sg_kwargs.update({'rule': '0'})

    li = -1
    for bi in range(nb_conv_blocks):
        for ci in range(nb_hidden_layers):
            # HIDDEN LAYERS
            # # # # # # # # # # # # # # #

            li += 1

            # Generate Layer name and config
            name = f'Neuron_b{bi}c{ci}' # f'Neuron Block {bi} Conv {ci}'
            ksi = kernel_size[li] if isinstance(kernel_size, list) else kernel_size
            si = stride[li] if isinstance(stride, list) else stride
            pi = padding[li] if isinstance(padding, list) else padding
            fi = nb_filters[li] if isinstance(nb_filters, list) else nb_filters
            recurrent = True if args.dataset == 'shd' else False
            connection_class = ConvConnection if args.dataset == 'shd' else Conv2dConnection
            fanout = ksi * fi if args.dataset == 'shd' else ksi * ksi * fi
            fanout = 2 * fanout if 'rfanout' in args.comments else fanout
            fanout = 1 if not 'fanout' in args.comments else fanout

            sg_kwargs.update({'fanout': fanout})
            act_fn = ConditionedSG(**sg_kwargs)
            neuron_kwargs = {
                'tau_mem': 20e-3,
                'tau_syn': 10e-3,
                'activation': act_fn,
                'comments': args.comments
            }

            # Make layer
            layer = ConvLayer(name=name,
                              model=model,
                              input_group=upstream_group,
                              kernel_size=ksi,
                              stride=si,
                              padding=pi,
                              nb_filters=fi,
                              recurrent=recurrent,
                              neuron_class=neuron_group,
                              neuron_kwargs=neuron_kwargs,
                              recurrent_connection_kwargs=recurrent_kwargs,
                              regs=regs,
                              connection_class=connection_class
                              )

            # Initialize Parameters
            initializer.initialize(layer)

            # Set output as input to next layer
            upstream_group = layer.output_group

        if args.dataset in ['dvs', 'cifar10']:
            # Make maxpool layer
            maxpool = model.add_group(
                MaxPool2d(upstream_group,
                          kernel_size=maxpool_kernel_size,
                          dropout_p=dropout_p)
            )

            upstream_group = maxpool

    # READOUT LAYER
    # # # # # # # # # # # # # # #
    readout_group = model.add_group(ReadoutGroup(
        nb_classes,
        tau_mem=tau_readout,
        tau_syn=neuron_kwargs['tau_syn'],
        initial_state=-1e-3))

    readout_connection = model.add_connection(Connection(upstream_group,
                                                         readout_group,
                                                         flatten_input=True))

    # Initialize readout connection
    readout_initializer.initialize(readout_connection)

    # #### Add monitors for spikes and membrane potential
    for layer in model.groups:
        if 'Neuron' in layer.name:
            model.add_monitor(stork.monitors.MeanFiringRateMonitor(layer))

    # #### Configure model for training
    model.configure(input=input_group,
                    output=readout_group,
                    loss_stack=loss_stack,
                    generator=generator,
                    optimizer=opt,
                    optimizer_kwargs=dict(lr=lr),
                    time_step=dt)

    # count number of trainable parameters
    results = {}
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f'Trainable parameters: {trainable_params}')
    results['n_params'] = trainable_params

    if args.plot_activity:
        # ## Monitoring activity before training
        fig = plt.figure(dpi=150)
        stork.plotting.plot_activity_snapshot(
            model,
            data=test_dataset,
            nb_samples=5,
            point_alpha=0.3)

        plotpath = os.path.join(args.log_dir, 'pre_activity.png')
        fig.savefig(plotpath, dpi=300)

    # ## Training
    # takes around 85 minutes using a powerful GPU

    print('Start training...')
    history = model.fit_validate(
        train_dataset,
        valid_dataset,
        nb_epochs=nb_epochs,
        verbose=False,
        monitor=True,
        stop_time=stop_time,
        shorten='test' in args.comments
    )

    print('history', history)

    results.update(history)

    # Free up some GPU space and clear cache
    # This might not be necessary for you if your GPU has enough memory
    del history
    gc.collect()
    torch.cuda.empty_cache()

    # ## Test

    print('Start testing...')
    scores = model.evaluate(test_dataset, shorten='test' in args.comments).tolist()
    results["test_loss"], _, results["test_acc"] = scores

    # #### Visualize performance
    fig, ax = plt.subplots(2, 2, figsize=(5, 3), dpi=150)

    for i, n in enumerate(["train_loss", "train_acc", "valid_loss", "valid_acc"]):

        if i < 2:
            a = ax[0][i]
        else:
            a = ax[1][i - 2]

        a.plot(results[n], color="black")
        a.set_xlabel("Epochs")
        a.set_ylabel(n)

    ax[0, 1].set_ylim(0, 1)
    ax[1, 1].set_ylim(0, 1)

    sns.despine()
    plt.tight_layout()

    plotpath = os.path.join(args.log_dir, 'training.png')
    plt.savefig(plotpath, dpi=300)

    print("Test loss: ", results["test_loss"])
    print("Test acc.: ", results["test_acc"])

    print("\nValidation loss: ", results["valid_loss"][-1])
    print("Validation acc.: ", results["valid_acc"][-1])

    if args.plot_activity:
        # #### Snapshot after training
        fig = plt.figure(dpi=150)
        stork.plotting.plot_activity_snapshot(
            model,
            data=test_dataset,
            nb_samples=5,
            point_alpha=0.3)
        plotpath = os.path.join(args.log_dir, 'post_activity.png')
        fig.savefig(plotpath, dpi=300)

    print(json.dumps(results, indent=4, cls=NumpyEncoder))
    return results


def parse_args():
    EXPSDIR = os.path.abspath(os.path.join(CDIR, '..', '..', 'experiments'))
    os.makedirs(EXPSDIR, exist_ok=True)

    named_tuple = time.localtime()  # get struct_time
    time_string = time.strftime("%Y-%m-%d--%H-%M-%S--", named_tuple)
    characters = string.ascii_letters + string.digits
    random_string = ''.join(random.choice(characters) for _ in range(5))

    log_dir = os.path.join(EXPSDIR, time_string + random_string + '_fluctuations')

    parser = argparse.ArgumentParser(description='Fluctuations-driven init experiments')
    parser.add_argument('--seed', type=int, default=0, help='CPU and GPU seed')
    parser.add_argument('--epochs', type=int, default=3, help='Epochs')
    parser.add_argument('--plot_activity', type=int, default=0, help='Plot activity before and after training')
    # shd and cifar10 on my laptop
    parser.add_argument('--dataset', type=str, default='cifar10', help='Name of dataset to use',
                        choices=datasets_available)
    # parser.add_argument('--comments', type=str, default='test', help='String to activate extra behaviors')
    parser.add_argument('--comments', type=str, default='test_reglag_smorms3_deep_condIV_muchange_lr:0.005',
                        help='String to activate extra behaviors')
    parser.add_argument("--stop_time", default=2000, type=int, help="Stop time (seconds)")
    parser.add_argument('--log_dir', type=str, default=log_dir, help='Name of subdirectory to save results in')
    args = parser.parse_args()

    os.makedirs(args.log_dir, exist_ok=True)

    return args


if __name__ == '__main__':
    args = parse_args()

    time_start = time.perf_counter()
    results = main(args)
    time_elapsed = (time.perf_counter() - time_start)

    results.update(time_elapsed=time_elapsed)
    results.update(hostname=socket.gethostname())

    args = args.__dict__
    for d in [args, results]:
        string_result = json.dumps(d, indent=4, cls=NumpyEncoder)
        var_name = [k for k, v in locals().items() if v is d if not k == 'd'][0]
        print(var_name)

        path = os.path.join(args['log_dir'], var_name + '.txt')
        with open(path, "w") as f:
            f.write(string_result)

    shutil.make_archive(args['log_dir'], 'zip', args['log_dir'])
    print('All done, in ' + str(time_elapsed) + 's')
