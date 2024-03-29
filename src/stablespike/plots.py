import os, json, argparse, copy
from datetime import timedelta, datetime

from pyaromatics.keras_tools.esoteric_initializers import glorotcolor, orthogonalcolor, hecolor
from pyaromatics.stay_organized.pandardize import simplify_col_names

os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
FMT = '%Y-%m-%dT%H:%M:%S'

from tqdm import tqdm
import pandas as pd
import matplotlib as mpl
import numpy as np
from matplotlib.lines import Line2D

import matplotlib.pyplot as plt

from pyaromatics.keras_tools.esoteric_layers.surrogated_step import possible_pseudod, clean_pseudname, \
    clean_pseudo_name, pseudod_color
from pyaromatics.keras_tools.plot_tools import plot_history, history_pick
from pyaromatics.stay_organized.unzip import unzip_good_exps
from pyaromatics.stay_organized.utils import timeStructured, str2val
from pyaromatics.stay_organized.mpl_tools import load_plot_settings

from pyaromatics.keras_tools.esoteric_tasks.time_task_redirection import Task
from stablespike.visualization_tools.plotting_tools import smart_plot, postprocess_results

mpl, pd = load_plot_settings(mpl=mpl, pd=pd)

CDIR = os.path.dirname(os.path.realpath(__file__))
EXPERIMENTS = os.path.join(CDIR, 'experiments')

GEXPERIMENTS = [
    # r'C:\Users\PlasticDiscobolus\work\stablespike\good_experiments',
    # r'D:\work\stochastic_spiking\good_experiments\2022-08-21--adaptsg',
    # r'D:\work\stochastic_spiking\good_experiments\2022-08-20--lr-grid-search',
    # r'C:\Users\PlasticDiscobolus\work\stochastic_spiking\good_experiments\2022-02-10--best-ptb-sofar',
    # r'E:\work\stochastic_spiking\good_experiments\2022-02-11--final_for_lif',
    # r'E:\work\stochastic_spiking\good_experiments\2022-09-17--sparsity-for-figure',
    r'E:\work\stochastic_spiking\good_experiments\2022-01-12--decent-SHD-conditions',
    # r'D:\work\stochastic_spiking\good_experiments\2022-02-16--verygood-ptb',
    # r'C:\Users\PlasticDiscobolus\work\stochastic_spiking\good_experiments\2022-02-16--verygood-ptb'
    # r'D:\work\stablespike\good_experiments\2023-11-01--ptblif',
]
EXPERIMENTS = r'E:\work\stochastic_spiking\experiments'

CSVPATH = os.path.join(EXPERIMENTS, 'means.h5')
HSITORIESPATH = os.path.join(EXPERIMENTS, 'histories.json')

# metric_sort = 'v_ppl'
metric_sort = 'val_macc'
# metrics_oi = ['v_ppl', 'v_macc', 't_ppl', 't_macc', 'fr_initial', 'fr_final', 'fr_1_initial', 'fr_1_final']
# metrics_oi = ['val_macc', 'macc_test']
metrics_oi = ['val_macc']
reduce_samples = False
group_cols = ['net_name', 'task_name', 'initializer', 'comments', 'lr']
group_cols = ['net_name', 'task_name', 'initializer', 'comments']

parser = argparse.ArgumentParser(description='main')
parser.add_argument(
    '--type', default='excel', type=str, help='main behavior',
    choices=[
        'excel', 'histories', 'interactive_histories', 'activities', 'weights', 'continue', 'robustness', 'init_sg',
        'pseudod', 'move_folders', 'conventional2spike', 'n_tail', 'task_net_dependence', 'sharpness_dampening',
        'conditions', 'lr_sg', 'sparsity'
    ]
)
args = parser.parse_args()

_, starts_at_s = timeStructured(False, True)

if not os.path.exists(CSVPATH):
    ds = unzip_good_exps(GEXPERIMENTS, EXPERIMENTS, exp_identifiers=['mnl'], unzip_what=['run.json'])
    ds = [d for d in ds if os.path.exists(os.path.join(d, 'other_outputs', 'history.json'))]

    histories = {}
    df = pd.DataFrame()
    list_results = []
    for d in tqdm(ds):

        history_path = os.path.join(d, 'other_outputs', 'history.json')
        hyperparams_path = os.path.join(d, 'other_outputs', 'results.json')
        config_path = os.path.join(d, '1', 'config.json')
        run_path = os.path.join(d, '1', 'run.json')

        with open(history_path) as f:
            history = json.load(f)

        if len(history['loss']) > 5:

            with open(config_path) as f:
                config = json.load(f)

            with open(run_path) as f:
                run = json.load(f)

            results = {}
            results.update({'where': run['host']['hostname']})

            if 'stop_time' in run.keys():
                results.update({'duration_experiment':
                                    datetime.strptime(run['stop_time'].split('.')[0], FMT) - datetime.strptime(
                                        run['start_time'].split('.')[0], FMT)
                                })
            # results.update({k: history_pick(k, v) for k, v in history.items()})
            results.update(h for k, v in history.items() for h in history_pick(k, v))

            results.update({k: v for k, v in config.items()})
            results.update({'d_name': d})

            if os.path.exists(hyperparams_path):
                with open(hyperparams_path) as f:
                    hyperparams = json.load(f)
                    if 'comments' in hyperparams.keys():
                        hyperparams['final_comments'] = hyperparams['comments']
                        hyperparams.pop('comments', None)

                results.update({k: postprocess_results(k, v) for k, v in hyperparams.items()})

            list_results.append(results)

            # df = df.append(small_df)
            history = {k.replace('val_', ''): v for k, v in history.items() if 'val' in k}

            histories[d] = history

    df = pd.DataFrame.from_records(list_results)
    df.loc[df['comments'].str.contains('noalif'), 'net_name'] = 'LIF'
    df.loc[df['net_name'].str.contains('maLSNN'), 'net_name'] = 'ALIF'
    df.loc[df['net_name'].str.contains('spikingLSTM'), 'net_name'] = 'sLSTM'

    df.loc[df['task_name'].str.contains('wordptb'), 'task_name'] = 'PTB'
    df.loc[df['task_name'].str.contains('heidelberg'), 'task_name'] = 'SHD'
    df.loc[df['task_name'].str.contains('sl_mnist'), 'task_name'] = 'sl-MNIST'

    cols = list(df)
    cols.insert(0, cols.pop(cols.index('convergence')))
    df = df.loc[:, cols]

    df = df.sort_values(by='comments')

    df.to_hdf(CSVPATH, key='df', mode='w')
    json.dump(histories, open(HSITORIESPATH, "w"))
else:
    # mdf = pd.read_csv(CSVPATH)
    df = pd.read_hdf(CSVPATH, 'df')  # load it
    with open(HSITORIESPATH) as f:
        histories = json.load(f)

print(list(df.columns))
history_keys = [
    'perplexity', 'sparse_mode_accuracy', 'loss',
    'v_perplexity', 'v_sparse_mode_accuracy', 'v_loss',
    't_perplexity', 't_sparse_mode_accuracy', 't_loss',
    'val_sparse_mode_accuracy', 'sparse_mode_accuracy_test',
    'firing_rate_ma_lsnn_initial', 'firing_rate_ma_lsnn_final',
    'firing_rate_ma_lsnn_1_initial', 'firing_rate_ma_lsnn_1_final',
    'v_firing_rate_ma_lsnn_initial', 'v_firing_rate_ma_lsnn_final',
    'v_firing_rate_ma_lsnn_1_initial', 'v_firing_rate_ma_lsnn_1_final',
    't_firing_rate_ma_lsnn_initial', 't_firing_rate_ma_lsnn_final',
    't_firing_rate_ma_lsnn_1_initial', 't_firing_rate_ma_lsnn_1_final',
]

df = df.rename(columns={
    "val_sparse_mode_accuracy max": "val_sparse_mode_accuracy", "loss min": "loss",
    # "sparse_mode_accuracy_test max": "sparse_mode_accuracy_test",
    "sparse_mode_accuracy_test_2": "sparse_mode_accuracy_test"
})

config_keys = ['comments', 'initializer', 'optimizer_name', 'seed', 'weight_decay', 'clipnorm', 'task_name', 'net_name']
hyperparams_keys = [
    'n_params', 'final_epochs', 'duration_experiment', 'convergence', 'lr', 'stack', 'n_neurons', 'embedding',
    'batch_size',
]
extras = ['d_name', 'where']  # , 'where', 'main_file','accumulated_epochs',

keep_columns = history_keys + config_keys + hyperparams_keys + extras
remove_columns = [k for k in df.columns if k not in keep_columns]
df.drop(columns=remove_columns, inplace=True)

df = simplify_col_names(df)


def fix_df_comments(df):
    df['comments'] = df['comments'].str.replace('_ptb2', '')
    for ps in possible_pseudod:
        df['comments'] = df['comments'].str.replace('timerepeat:2' + ps, 'timerepeat:2_' + ps)

    # df = df[df['task_name'].str.contains('PTB')]
    # df = df[df['comments'].str.contains('_v0m')]
    # df = df[df['d_name'] > r'C:\Users\PlasticDiscobolus\work\stablespike\experiments\2022-08-13']
    # df = df[~(df['d_name'].str.contains('2022-08-10--')) | (df['d_name'].str.contains('2022-08-11--'))]

    # df = df[(df['d_name'].str.contains('2022-08-12--'))|(df['d_name'].str.contains('2022-08-13--'))]
    # df = df[(df['d_name'].str.contains('2022-08-27--'))]
    df['comments'] = df['comments'].replace({'1_embproj_nogradres': '6_embproj_nogradres'}, regex=True)
    return df


df = fix_df_comments(df)

print(df.columns)
early_cols = ['task_name', 'net_name', 'loss', *metrics_oi, 'n_params', 'final_epochs', 'comments']
some_cols = [n for n in list(df.columns) if not n in early_cols]
df = df[early_cols + some_cols]

# print(df['duration_experiment'])

# group_cols = ['net_name', 'task_name', 'initializer', 'comments', 'lr']
# only 4 experiments of the same type, so they have comparable statistics

if reduce_samples or args.type == 'lr_sg':
    df = df.sort_values(by='d_name', ascending=True)
    df = df.groupby(group_cols).sample(4, replace=True)

df = df.sort_values(by=metric_sort, ascending=False)
print(df.to_string())

counts = df.groupby(group_cols).size().reset_index(name='counts')

mdf = df.groupby(group_cols, as_index=False).agg({m: ['mean', 'std'] for m in metrics_oi})

for metric in metrics_oi:
    mdf['mean_{}'.format(metric)] = mdf[metric]['mean']
    mdf['std_{}'.format(metric)] = mdf[metric]['std']
    mdf = mdf.drop([metric], axis=1)

mdf['counts'] = counts['counts']
mdf = mdf.sort_values(by='mean_' + metric_sort, ascending=False)

print(mdf.to_string())

_, ends_at_s = timeStructured(False, True)
duration_experiment = timedelta(seconds=ends_at_s - starts_at_s)
print('Time to load the data: ', str(duration_experiment))

# print(mdf.to_string())
if args.type == 'excel':

    # df = df[df['d_name'].str.contains('2021-12-29')]
    tasks = np.unique(df['task_name'])

    for task in tasks:
        print(task)
        idf = df[df["task_name"] == task]
        idf = idf.sort_values(
            by=['val_macc' if not task in ['wordptb', 'PTB'] else 'val_bpc'],
            ascending=False if not task in ['wordptb', 'PTB'] else True
        )
        print(idf.to_string(index=False))
        print('\n\n')

    # print(df.to_string(index=False))
    print(df.shape)


elif args.type == 'n_tail':
    metric = 'val_macc'
    idf = df[df['comments'].str.contains('_tailvalue') & df['comments'].str.contains('2_')]
    counts = idf.groupby(['comments', ]).size().reset_index(name='counts')
    left = counts[counts['counts'] < 4]
    done = counts[counts['counts'] == 4]['comments'].values
    print('done:')
    print(done)

    print()
    idf = mdf[mdf['comments'].str.contains('2_')]
    print('is mdf fine?')
    print(mdf.to_string(index=False))
    print(idf.to_string(index=False))
    idf = idf.loc[idf['comments'].isin(done)]
    idf = idf.sort_values(by=f'mean_{metric}', ascending=False)
    print('here!')
    print(idf.to_string(index=False))

    idf = idf[idf['comments'].str.contains('tailvalue')]
    tails = idf['comments'].str.replace(
        '2_noalif_timerepeat:2_multreset2_nogradreset__ntailpseudod_tailvalue:', ''
    ).values.astype(float)

    sorted_idx = tails.argsort()
    accs = idf[f'mean_{metric}'].values[sorted_idx]
    stds = idf[f'std_{metric}'].values[sorted_idx]
    tails = tails[sorted_idx]

    cm = plt.get_cmap('Oranges')
    # print(idf.to_string(index=False))
    fig, axs = plt.subplots(1, 1, gridspec_kw={'wspace': .0, 'hspace': 0.}, figsize=(4, 4))
    axs.plot(tails, accs, color=cm(.5))
    axs.fill_between(tails, accs - stds, accs + stds, alpha=0.5, color=cm(.5))

    value = 1.8984
    axs.axvline(x=value, color='k', linestyle='--')

    for pos in ['right', 'left', 'bottom', 'top']:
        axs.spines[pos].set_visible(False)

    axs.set_xlabel('$q$ Tail fatness')
    axs.set_xscale('log')
    axs.set_yticks([0.89, .9, .91])

    # axs[1].set_ylabel('mean gradient\nmagnitude')
    axs.set_ylabel('Validation Accuracy')
    plot_filename = r'experiments/figure2_tails.pdf'
    fig.savefig(plot_filename, bbox_inches='tight')

    plt.show()

    print(counts)
    print(left)
    print(done)


elif args.type == 'sharpness_dampening':
    feature = 'sharpness'  # sharpness dampening
    features = ['sharpness']
    for feature in features:
        feature_oi = 'dampf' if feature == 'dampening' else 'sharpn'

        idf = mdf[mdf['comments'].str.contains('2_')]

        idf = idf[idf['comments'].str.contains(feature_oi)]
        idf = idf[idf['net_name'].str.contains('LIF')]
        idf = idf[idf['task_name'].str.contains('sl-MNIST')]
        print(idf.to_string(index=False))

        comments = np.unique(mdf['comments'])
        fig, axs = plt.subplots(1, 1, gridspec_kw={'wspace': .0, 'hspace': 0.}, figsize=(4, 4))

        for pn in possible_pseudod:
            iidf = idf[idf['comments'].str.contains(pn)].sort_values(by='comments', ascending=False)
            foi_values = [str2val(d, feature_oi) for d in iidf['comments']]
            print(foi_values)
            accs = iidf['mean_val_macc'].values
            stds = iidf['std_val_macc'].values
            stds = np.nan_to_num(stds)
            if feature == 'sharpness':
                if 0.1 in foi_values:
                    foi_values = foi_values[:-1]
                    accs = accs[:-1]
                    stds = stds[:-1]
            axs.plot(foi_values, accs, color=pseudod_color(pn))
            axs.fill_between(foi_values, accs - stds, accs + stds, alpha=0.5, color=pseudod_color(pn))

        value = .204 if feature == 'dampening' else 1.02
        axs.axvline(x=value, color='k', linestyle='--')
        for pos in ['right', 'left', 'bottom', 'top']:
            axs.spines[pos].set_visible(False)

        axs.set_yticks([.9, .7, .5, .3, .1])
        axs.set_xlabel(feature.capitalize())
        axs.set_ylabel('Validation Accuracy')
        plot_filename = r'experiments/figure2_{}.pdf'.format(feature)
        fig.savefig(plot_filename, bbox_inches='tight')

        plt.show()

        idf = df[df['comments'].str.contains('1_')]
        idf = idf[idf['comments'].str.contains(feature_oi)]
        idf = idf[idf['net_name'].str.contains('ALIF')]
        idf = idf[idf['task_name'].str.contains('sl-MNIST')]

        counts = idf.groupby(['comments', ]).size().reset_index(name='counts')
        left = counts[counts['counts'] < 4]
        print(counts)
        print(left)


elif args.type == 'lr_sg':
    normalize_ppls = True


    def sensitivity_metric(out_vars, in_vars, name='mean'):
        assert out_vars.keys() == in_vars.keys()
        lrs = out_vars.keys()
        if name == 'ratio':
            metric = np.mean([out_vars[lr] / in_vars[lr] for lr in lrs])
        elif name == 'mean':
            metric = np.mean([out_vars[lr] for lr in lrs])
        elif name == 'diff':
            metric = np.mean([abs(out_vars[lr] - in_vars[lr]) for lr in lrs])
        else:
            raise NotImplementedError

        return metric


    per_task_variability = {}
    metric = 'v_ppl'

    net_name = 'LIF'  # LIF sLSTM
    all_tasks = ['sl-MNIST', 'SHD', 'PTB']  # for LIF
    all_nets = ['LIF', 'ALIF', 'sLSTM']
    task_sensitivity = {}
    net_sensitivity = {}
    task_sensitivity_std = {}
    net_sensitivity_std = {}

    fig, axs = plt.subplots(
        2, 3 + 1, figsize=(12, 5),
        gridspec_kw={'wspace': .5, 'hspace': .5, 'width_ratios': [1, 1, 1, 1.3]}
    )

    # if not isinstance(axs, list):
    #     axs = [axs]

    mdf = mdf[mdf['comments'].str.contains('6_')]
    mdf = mdf[mdf['comments'].str.contains('_dropout:.3')]
    df = df[df['comments'].str.contains('6_')]
    df = df[df['comments'].str.contains('_dropout:.3')]
    maxs = {}
    mins = {}
    for t in all_tasks:
        maxs[t] = {}
        mins[t] = {}
        for n in all_nets:
            idf = df[(df['task_name'].eq(t)) & (df['net_name'].eq(n))]
            maxs[t][n] = idf[metric].max()
            mins[t][n] = idf[metric].min()

    print(maxs)
    print(mins)
    # plot lr vs metric
    for i, (tasks, nets) in enumerate([[all_tasks, ['LIF']], [['SHD'], all_nets]]):
        for j, net_name in enumerate(nets):
            for k, task in enumerate(tasks):
                idf = mdf
                idf = idf[idf['net_name'].eq(net_name)]
                idf = idf[idf['task_name'].str.contains(task)]
                idf = idf.sort_values(by=['mean_' + metric], ascending=False)

                # print(idf.to_string(index=False))

                comments = np.unique(mdf['comments'])
                for pn in possible_pseudod:
                    iidf = idf[idf['comments'].str.contains(pn)]
                    lrs = np.unique(iidf['lr'])

                    accs = []
                    stds = []
                    for lr in lrs:
                        ldf = iidf[iidf['lr'] == lr]
                        accs.append(ldf['mean_' + metric].values[0])
                        stds.append(ldf['std_' + metric].values[0] / 2)

                    stds = np.nan_to_num(stds)

                    axs[i, j + k].plot(lrs, accs, color=pseudod_color(pn))
                    axs[i, j + k].fill_between(lrs, accs - stds, accs + stds, alpha=0.5, color=pseudod_color(pn))

                axs[i, j + k].set_title(task if i == 0 else net_name)

    # compute sensitivities
    for i, (tasks, nets) in enumerate([[all_tasks, ['LIF']], [['SHD'], all_nets]]):
        for j, net_name in enumerate(nets):
            for k, task in enumerate(tasks):
                print('-' * 30)
                print(task)
                sdf = df[df['net_name'].eq(net_name)]
                sdf = sdf[sdf['comments'].str.contains('6_embproj_')]
                sdf = sdf[sdf['task_name'].str.contains(task)]

                # print(idf2.to_string())
                items = -1
                if task == 'sl-MNIST':
                    items = 10
                elif task == 'SHD':
                    items = 20
                elif task == 'PTB':
                    items = 10000

                lrs = np.unique(sdf['lr'])
                out_vars = {}
                pn_vars = {pn: {} for pn in possible_pseudod}
                for lr in lrs:
                    sdf_lr = sdf[sdf['lr'].eq(lr)]

                    if normalize_ppls:
                        sdf_lr[metric] = (sdf_lr[metric] - mins[task][net_name]) / (
                                maxs[task][net_name] - mins[task][net_name])
                    out_vars[lr] = sdf_lr[metric].std()

                    for pn in possible_pseudod:
                        sdf_lr_pn = sdf_lr[sdf_lr['comments'].str.contains(pn)]
                        pn_vars[pn][lr] = sdf_lr_pn[metric].std()

                in_vars = {lr: np.mean([pn_vars[pn][lr] for pn in possible_pseudod]) for lr in lrs}

                # print(out_vars)
                if i == 0:
                    task_sensitivity[task] = sensitivity_metric(out_vars, in_vars)
                    task_sensitivity_std[task] = np.std([out_vars[lr] for lr in lrs])
                    print(task, task_sensitivity[task], task_sensitivity_std[task])
                else:
                    net_sensitivity[net_name] = sensitivity_metric(out_vars, in_vars)
                    net_sensitivity_std[net_name] = np.std([out_vars[lr] for lr in lrs])
                    print(net_name, net_sensitivity[net_name], net_sensitivity_std[net_name])

    for j in range(2):
        for i in range(3):
            axs[j, i].set_xscale('log')
            axs[j, i].set_xticks([1e-2, 1e-3, 1e-4, 1e-5])

        for i in range(3 + 1):
            for pos in ['right', 'left', 'bottom', 'top']:
                axs[j, i].spines[pos].set_visible(False)

    axs[1, 2].set_xlabel('Learning rate')
    axs[0, 0].set_ylabel('Validation Perplexity')

    axs[0, -1].bar(all_tasks, task_sensitivity.values(),
                   yerr=np.array(list(task_sensitivity_std.values())) / 2, color='maroon', width=0.6)
    axs[0, -1].set_ylabel('Sensitivity')
    axs[0, -1].set_xlabel('Task')

    axs[1, -1].bar(all_nets, net_sensitivity.values(),
                   yerr=np.array(list(net_sensitivity_std.values())) / 2, color='maroon', width=0.6)
    axs[1, -1].set_ylabel('Sensitivity')
    axs[1, -1].set_xlabel('Neural Model')

    axs[0, 0].text(-.7, .5, 'LIF network', fontsize=18,
                   horizontalalignment='center', verticalalignment='center', rotation='vertical',
                   transform=axs[0, 0].transAxes)
    axs[1, 0].text(-.7, .5, 'SHD task', fontsize=18,
                   horizontalalignment='center', verticalalignment='center', rotation='vertical',
                   transform=axs[1, 0].transAxes)

    axs[0, 0].set_yticks([2, 4, 6, 8, 10])
    axs[0, 2].set_yticks([100, 650, 1200])

    for i in [0, 1]:
        box = axs[i, -1].get_position()
        box.x0 = box.x0 + 0.05
        box.x1 = box.x1 + 0.05
        axs[i, -1].set_position(box)

    for i, label in enumerate('abcg'):
        axs[0, i].text(-.1, 1.2, f'{label})', fontsize=14, color='#535353',
                       horizontalalignment='center', verticalalignment='center',
                       transform=axs[0, i].transAxes)

    for i, label in enumerate('defh'):
        axs[1, i].text(-0.1, 1.2, f'{label})', fontsize=14, color='#535353',
                       horizontalalignment='center', verticalalignment='center',
                       transform=axs[1, i].transAxes)
        if 0 < i < 3:
            axs[1, i].sharey(axs[1, 0])

    # axs[1, i].sharey(axs[1, 0])

    legend_elements = [Line2D([0], [0], color=pseudod_color(n), lw=4, label=clean_pseudname(n))
                       for n in possible_pseudod]
    # plt.legend(ncol=3, handles=legend_elements, loc='lower center', bbox_to_anchor=(-1.4, -.85))

    plt.show()
    plot_filename = f'experiments/lr_sg.pdf'
    fig.savefig(plot_filename, bbox_inches='tight')



elif args.type == 'sparsity':
    from scipy import stats

    n_cols = 4
    n_rows = 1
    alpha = .7
    data_split = 't_'  # v_ t_ ''
    metric = 'ppl'  # macc ppl
    ylabel = 'Perplexity' if metric == 'ppl' else 'Accuracy'
    metric = data_split + metric
    task_name = 'PTB'  # sl-MNIST SHD PTB

    net_name = 'LIF'  # LIF sLSTM
    change_sg = 'fastsigmoidpseudod'  # exponentialpseudod originalpseudod fastsigmoidpseudod
    pseudoname = clean_pseudname(change_sg if len(change_sg) else 'fastsigmoidpseudod')

    plot_1, plot_2, plot_3 = True, False, False

    legend_elements = [
        Line2D([], [], color='darksalmon', marker='o', linestyle='None', alpha=alpha,
               markersize=10, label='layer 1'),
        Line2D([], [], color='sienna', marker='o', linestyle='None', alpha=alpha,
               markersize=10, label='layer 2'),
    ]

    mdf = mdf[mdf['comments'].str.contains('7_')]
    mdf = mdf[mdf['task_name'].str.contains(task_name)]
    df = df[df['comments'].str.contains('7_')]
    df = df[df['comments'].str.contains('_v0m')]
    df = df[df['task_name'].str.contains(task_name)]

    print(len(change_sg))
    if not change_sg == 'fastsigmoidpseudod':
        mdf = mdf[mdf['comments'].str.contains(change_sg)]
        df = df[df['comments'].str.contains(change_sg)]
    else:
        mdf = mdf[~mdf['comments'].str.contains('pseudod')]
        df = df[~df['comments'].str.contains('pseudod')]

    if plot_1:
        fig, axs = plt.subplots(
            n_rows, n_cols, figsize=(9, 5),
            gridspec_kw={'wspace': .2, 'hspace': .5},
            sharey=True
        )

        fig.legend(ncol=2, handles=legend_elements, loc='lower center', bbox_to_anchor=(0.5, -.2))
        ps = []
        rs = []
        # plot lr vs metric
        idf = df
        idf = idf[~idf['comments'].str.contains('adjff')]

        print(idf.columns)
        frs0i = idf[data_split + 'fr_initial'].values
        frs1i = idf[data_split + 'fr_1_initial'].values
        frs0f = idf[data_split + 'fr_final'].values
        frs1f = idf[data_split + 'fr_1_final'].values

        accs = idf[metric].values

        r0, p0 = stats.pearsonr(accs, frs0i)
        r0 = r0.round(2)
        r1, p1 = stats.pearsonr(accs, frs1i)
        r1 = r1.round(2)
        ps.extend([p0, p1])
        rs.extend([r0, r1])
        print(r0, p0, r1, p1)
        print(rs, ps)

        axs[0].scatter(frs0i, accs, alpha=alpha, color='darksalmon', label=f'$r_1=${r0}')
        axs[0].scatter(frs1i, accs, alpha=alpha, color='sienna', label=f'$r_2=${r1}')
        axs[0].set_xlabel('Initial\nfiring rate')

        r0, p0 = stats.pearsonr(accs, frs0f)
        r0 = r0.round(2)
        r1, p1 = stats.pearsonr(accs, frs1f)
        r1 = r1.round(2)
        ps.extend([p0, p1])
        rs.extend([r0, r1])
        print(r0, p0, r1, p1)
        print(rs, ps)

        axs[1].scatter(frs0f, accs, alpha=alpha, color='darksalmon', label=f'$r_1=${r0}')
        axs[1].scatter(frs1f, accs, alpha=alpha, color='sienna', label=f'$r_2=${r1}')
        axs[1].set_xlabel('Final\nfiring rate')

        idf = df
        # idf = idf[idf['comments'].str.contains('adjff:.01')]
        idf = idf[idf['comments'].str.contains('adjff')]

        frs0i = idf[data_split + 'fr_initial'].values
        frs1i = idf[data_split + 'fr_1_initial'].values
        frs0f = idf[data_split + 'fr_final'].values
        frs1f = idf[data_split + 'fr_1_final'].values
        accs = idf[metric].values

        r0, p0 = stats.pearsonr(accs, frs0i)
        r0 = r0.round(2)
        r1, p1 = stats.pearsonr(accs, frs1i)
        r1 = r1.round(2)
        ps.extend([p0, p1])
        rs.extend([r0, r1])
        print(r0, p0, r1, p1)
        print(rs, ps)

        axs[2].scatter(frs0i, accs, alpha=alpha, color='darksalmon', label=f'$r_1=${r0}')
        axs[2].scatter(frs1i, accs, alpha=alpha, color='sienna', label=f'$r_2=${r1}')
        axs[2].set_xlabel('Initial\nfiring rate')

        r0, p0 = stats.pearsonr(accs, frs0f)
        r0 = r0.round(2)
        r1, p1 = stats.pearsonr(accs, frs1f)
        r1 = r1.round(2)
        ps.extend([p0, p1])
        rs.extend([r0, r1])
        print(r0, p0, r1, p1)
        print(rs, ps)

        axs[3].scatter(frs0f, accs, alpha=alpha, color='darksalmon', label=f'$r_1=${r0}')
        axs[3].scatter(frs1f, accs, alpha=alpha, color='sienna', label=f'$r_2=${r1}')
        axs[3].set_xlabel('Final\nfiring rate')

        if 'v_' in data_split:
            ylabel = 'Validation ' + ylabel
        elif 't_' in data_split:
            ylabel = 'Test ' + ylabel
        else:
            ylabel = 'Train ' + ylabel
        axs[0].set_ylabel(ylabel)

        i = 0
        for ax in axs.reshape(-1):
            bbox_to_anchor = (0.5, .65) if not task_name == 'PTB' else (0.5, .4)
            l = ax.legend(loc='lower center', bbox_to_anchor=bbox_to_anchor, handlelength=0, handletextpad=0,
                          fancybox=True,
                          facecolor=(1, 1, 1, 0.8))

            for item in l.legendHandles:
                item.set_visible(False)

            for t in l.get_texts():
                print(ps[i], rs[i])
                if ps[i] < 0.05:
                    t.set_weight('bold')
                i += 1

            for pos in ['right', 'left', 'bottom', 'top']:
                ax.spines[pos].set_visible(False)

            if task_name == 'sl-MNIST':
                ax.set_xlim([-0.1, 0.8])
            else:
                ax.set_xlim([0.0, 0.8])

            ax.set_xticks([0.25, 0.5, 0.75])
            ax.locator_params(nbins=5)

        for j in range(4):
            if not j == 0:
                axs[j].tick_params(axis='y', which='both', left=False, right=False, labelleft=False)

        fig.text(0.72, .93, 'Sparsity Encouraging\nLoss Term', ha='center', va='center', fontsize=16)
        fig.text(0.29, .93, 'no Sparsity Encouraging\nLoss Term', ha='center', va='center', fontsize=16)
        plt.suptitle(f'{pseudoname} on {task_name}', y=1.07)
        # line = plt.Line2D([.52, .52], [-.05, .95], transform=fig.transFigure, color="black")
        line = plt.Line2D([.52, .52], [-.05, .95], transform=fig.transFigure, color="black")
        fig.add_artist(line)

        plt.show()
        plot_filename = f'experiments/{data_split}_sparsity_tsg{change_sg}_t{task_name}.pdf'
        fig.savefig(plot_filename, bbox_inches='tight')

    if plot_2:
        fig, axs = plt.subplots(
            2, 1, figsize=(12, 7),
            gridspec_kw={'wspace': .5, 'hspace': .5},
            sharey=True
        )

        for i, adj in enumerate([True, False]):
            idf = df
            if adj:
                idf = idf[idf['comments'].str.contains('adjff')]
            else:
                idf = idf[~idf['comments'].str.contains('adjff')]

            for _, row in idf.iterrows():
                hyperparams_path = os.path.join(row['d_name'], 'other_outputs', 'results.json')

                with open(hyperparams_path) as f:
                    results = json.load(f)

                loss = results['firing_rate_ma_lsnn_sparsification']
                axs[i].plot(loss)
                loss = results['firing_rate_ma_lsnn_1_sparsification']
                axs[i].plot(loss)

        fig.suptitle('pretraining')
        plt.show()

    if plot_3:
        fig, axs = plt.subplots(
            2, 1, figsize=(12, 7),
            gridspec_kw={'wspace': .5, 'hspace': .5},
            sharey=True
        )

        for i, adj in enumerate([True, False]):
            idf = df
            if adj:
                idf = idf[idf['comments'].str.contains('adjff')]
            else:
                idf = idf[~idf['comments'].str.contains('adjff')]

            for _, row in idf.iterrows():
                hyperparams_path = os.path.join(row['d_name'], 'other_outputs', 'history.json')

                with open(hyperparams_path) as f:
                    results = json.load(f)

                loss = results['firing_rate_ma_lsnn']
                axs[i].plot(loss)
                loss = results['firing_rate_ma_lsnn_1']
                axs[i].plot(loss)

        fig.suptitle('training')
        plt.show()

elif args.type == 'init_sg':

    mini_df = df[df['comments'].str.contains('3_')]
    print(mini_df.to_string())
    idf = mdf[mdf['comments'].str.contains('3_')]

    idf['comments'] = idf['comments'].str.replace('3_embproj_snudecay_', '')
    idf['comments'] = idf['comments'].str.replace('3_noalif_timerepeat:2_multreset2_nogradreset_', '')
    idf['initializer'] = idf['initializer'].str.replace('BiGammaOrthogonal', 'OBiGamma')
    idf['initializer'] = idf['initializer'].str.replace('Orthogonal', 'OrthogonalNormal')
    idf['initializer'] = idf['initializer'].str.replace('OBiGamma', 'OrthogonalBiGamma')

    pseudods = possible_pseudod  # np.unique(idf['comments'])
    desired_initializers = ['HeNormal', 'HeUniform', 'HeBiGamma', 'GlorotNormal', 'GlorotUniform', 'GlorotBiGamma',
                            'OrthogonalNormal', 'OrthogonalBiGamma']
    # desired_initializers = ['HeBiGamma', 'GlorotBiGamma', 'OrthogonalBiGamma']

    print(mini_df.to_string(index=False))
    print(idf.to_string(index=False))
    idf = idf[['mean_val_macc', 'std_val_macc', 'comments', 'initializer']]
    idf = idf.loc[idf['initializer'].isin(desired_initializers)]
    idf['initializer'] = idf['initializer'].str.replace('BiGamma', ' BiGamma')
    idf['initializer'] = idf['initializer'].str.replace('Normal', ' Normal')
    idf['initializer'] = idf['initializer'].str.replace('Uniform', ' Uniform')

    idf = idf.sort_values(by=['mean_val_macc'], ascending=False)
    print(idf.to_string(index=False))

    # fig, axs = plt.subplots(1, 1, gridspec_kw={'wspace': .0, 'hspace': 0.}, figsize=(15, 5))

    fig = plt.figure(figsize=(15, 5))

    gs = fig.add_gridspec(1, 4, wspace=0.3)
    ax1 = fig.add_subplot(gs[0, :2])
    ax2 = fig.add_subplot(gs[0, 2])
    ax3 = fig.add_subplot(gs[0, 3])

    x = np.arange(len(desired_initializers))  # the label locations
    width = 1 / (len(pseudods) + 1)  # the width of the bars
    for i in range(len(pseudods)):
        c = pseudod_color(pseudods[i])
        # iidf = idf[idf['comments'] == pseudods[i]]
        iidf = idf[idf['comments'].str.contains(pseudods[i])]
        iidf = iidf.sort_values('initializer')
        print(iidf)
        if not iidf.empty:
            ax1.bar(
                x + i * width - (len(pseudods) - 1) / 2 * width,
                iidf['mean_val_macc'].values,
                yerr=iidf['std_val_macc'].values, width=width, color=c
            )
    ax1.set_ylim([.6, .9])
    clean_initializers_n = [
        d.replace('BiGammaOrthogonal', 'OrthogonalBiGamma').replace('Normal', ' Normal')
        .replace('Uniform', ' Uniform').replace('BiGamma', ' BiGamma')
        for d in desired_initializers]

    ax1.set_xticks(np.arange(len(desired_initializers)))
    ax1.set_xticklabels(clean_initializers_n)
    ax1.set_ylabel('Validation Accuracy')

    import seaborn as sns


    def init_color(name):
        if 'orot' in name:
            color = glorotcolor
        elif 'rthogonal' in name:
            color = orthogonalcolor
        else:
            color = hecolor
        return color


    idf['comments'] = idf['comments'].apply(clean_pseudname)
    palette = {p: init_color(p) for p in clean_initializers_n}
    sns.boxplot(y='mean_val_macc', x='initializer', data=idf, ax=ax2, palette=palette)
    ax2.set_ylabel('')
    # ax.set_xticklabels(x_labels, rotation='vertical', ha='center')
    ax2.set_xlabel('')
    # ax2.set_ylim([.7, .88])

    palette = {clean_pseudname(p): pseudod_color(p) for p in possible_pseudod}
    sns.boxplot(y='mean_val_macc', x='comments', data=idf, ax=ax3, palette=palette)
    ax3.set_ylabel('')
    ax3.set_xlabel('')

    for tick in [*ax2.get_xticklabels(), *ax3.get_xticklabels(), *ax1.get_xticklabels()]:
        tick.set_rotation(45)
        tick.set_ha('right')

    for pos in ['right', 'left', 'bottom', 'top']:
        ax1.spines[pos].set_visible(False)
        ax2.spines[pos].set_visible(False)
        ax3.spines[pos].set_visible(False)

    ax1.tick_params(axis='x', labelsize=14)
    ax2.tick_params(axis='x', labelsize=14)
    ax3.tick_params(axis='x', labelsize=14)

    plot_filename = r'experiments/figure3_initializations.pdf'
    fig.savefig(plot_filename, bbox_inches='tight')
    plt.show()

    idf = df[df['comments'].str.contains('3_')]
    idf['initializer'] = idf['initializer'].str.replace('BiGammaOrthogonal', 'OrthogonalBiGamma')

    idf = idf.loc[idf['initializer'].isin(desired_initializers)]
    counts = idf.groupby(['comments', 'initializer']).size().reset_index(name='counts')
    left = counts[counts['counts'] < 4]
    print(counts)
    print(left)


elif args.type == 'conditions':
    option = 2

    idf = mdf[mdf['comments'].str.contains('5_')]
    idf = idf[idf['task_name'].str.contains('SHD')]
    print(idf.to_string())
    idf['comments'] = idf['comments'].str.replace('condition', '')
    idf['comments'] = idf['comments'].str.replace('timerepeat:2_', '')
    idf['comments'] = idf['comments'].str.replace('5_noalif_exponentialpseudod_', '')
    # idf['comments'] = idf['comments'].str.replace('', 'naive')
    idf['comments'] = idf['comments'].str.replace(r'_$', '')
    idf['comments'] = idf['comments'].str.replace('_', '+')
    # idf['comments'] = idf['comments'].str.replace('II+I+', 'I+II\n')
    # idf = idf.replace(r'^\s*$', 'naive', regex=True)

    order_conditions = idf['comments']
    print(idf)
    order_conditions = ['naive', 'I', 'II', 'III', 'IV:b', 'II+I', 'II+I+III', 'II+I+III+IV:b']
    # order_conditions = ['naive', 'I', 'II', 'III', 'IV', 'I+II', 'I+II+III', 'I+II+III+IV']
    idf = idf[idf['comments'].isin(order_conditions)]
    idf['comments'] = idf['comments'].str.replace('IV:b', 'IV')
    # idf['comments'] = idf['comments'].str.replace('+III', '\n+III')
    idf['comments'] = idf['comments'].apply(lambda x: "I+II" + x[4:] if x.startswith("II+I") else x)
    idf['comments'] = idf['comments'].apply(lambda x: x.replace('+III', '\n+III'))
    idf['comments'] = idf['comments'].apply(lambda x: x.replace('+IV', '\n+IV'))

    idf = idf.sort_values(by='mean_macc_test', ascending=True)  # mean_test_macc mean_val_macc
    order_conditions = idf['comments'].values
    order_conditions = ['no\nconditions' if o == 'naive' else o for o in order_conditions]
    print(idf)
    print(order_conditions)
    means_val = idf['mean_val_macc'].values
    stds_val = idf['std_val_macc'].values
    means_test = idf['mean_macc_test'].values
    stds_test = idf['std_macc_test'].values

    fig, axs = plt.subplots(2, 1, figsize=(5, 6))
    niceblue = '#0883E0'
    colors = [niceblue, '#97A7B3', niceblue, niceblue, niceblue, niceblue, niceblue, niceblue]

    axs[1].bar(range(len(means_val)), means_val, yerr=stds_val, width=.8, color=colors)
    axs[0].bar(range(len(means_test)), means_test, yerr=stds_test, width=.8, color=colors)
    axs[1].set_ylim([.77, .95])
    axs[1].set_yticks([.8, .85, .9, .95])
    axs[0].set_ylim([.62, .8])
    axs[0].set_yticks([.65, .7, .75, .8])
    axs[0].set_xticks([])
    axs[1].set_xticks(np.arange(len(order_conditions)))
    axs[1].set_xticklabels(order_conditions, ha='center')
    axs[1].set_xlabel('Conditions')
    axs[1].set_ylabel('Validation Accuracy')
    axs[0].set_ylabel('Test Accuracy')
    fig.align_ylabels(axs[:])

    for ax in axs:
        for pos in ['right', 'left', 'bottom', 'top']:
            ax.spines[pos].set_visible(False)

    plot_filename = r'experiments/figure5_conditions.pdf'
    fig.savefig(plot_filename, bbox_inches='tight')
    plt.show()



elif args.type == 'task_net_dependence':

    idf = df[df['comments'].str.contains('1_')]
    idf = idf[~idf['comments'].str.contains('sharpn')]
    idf = idf[~idf['comments'].str.contains('dampf')]
    # idf = idf[idf['d_name'].str.contains('2021-12')]
    idf = idf[~idf['task_name'].str.contains('s_mnist')]

    # idf['comments'] = idf['comments'].str.replace('dampf:1.0', '')
    idf['comments'] = idf['comments'].str.replace('1_embproj_', '')
    idf['comments'] = idf['comments'].str.replace('snudecay_', '')
    idf['comments'] = idf['comments'].str.replace('noalif_', '')

    idf = idf[~idf['comments'].str.contains('dampf')]
    idf = idf[~idf['comments'].str.contains('cauchypseudod')]
    idf = idf[~idf['comments'].str.contains('annealing')]
    idf = idf[idf['comments'].str.contains('pseudod')]

    figsize = (16, 8)

    # print(idf.to_string(index=False))
    # print(idf.shape, ' when it should be ', )
    counts = idf.groupby(['task_name', 'net_name', 'comments']).size().reset_index(name='counts')
    # print(counts.to_string(index=False))

    what2plot = ['net', 'task', ]
    fig, axs = plt.subplots(len(what2plot), 3, gridspec_kw={'wspace': 0.1, 'hspace': .4}, figsize=figsize, sharey=False)
    # plt.subplots_adjust(right=0.9)
    # tasks:
    for ci, choice in enumerate(what2plot):  # ['task', 'net']:
        axs[ci, 0].set_ylabel('loss')

        print('\nDependency on {} choice'.format(choice))
        if choice == 'task':
            choices = ['SHD', 'sl-MNIST', 'PTB']  # np.unique(idf['task_name'])
            iidf = idf[idf['net_name'] == 'LIF']
            min_loss_len = 0
        elif choice == 'net':
            choices = ['LIF', 'ALIF', 'sLSTM']  # np.unique(idf['net_name'])
            iidf = idf[idf['task_name'].str.contains('SHD')]
            min_loss_len = 100

        for a_i, c in enumerate(choices):

            for pos in ['right', 'left', 'bottom', 'top']:
                axs[ci, a_i].spines[pos].set_visible(False)

            if not (a_i, ci) == (0, 1):
                print(c)

                iiidf = iidf[iidf['{}_name'.format(choice)].str.strip() == c]
                loss_curves = {k: [] for k in possible_pseudod}

                for _, row in iiidf.iterrows():
                    ptype = str2val(row['comments'], 'pseudod', str, equality_symbol='', remove_flag=False)
                    if ptype in possible_pseudod:
                        curve = histories[row['d_name']]['sparse_categorical_crossentropy']
                        if len(curve) > min_loss_len:
                            loss_curves[ptype].append(curve)
                            # axs[a_i].plot(curve, label='train xe', color=pseudod_color(ptype), linestyle=(0, (5, 3)),
                            #               linewidth=.5)

                min_len = 200
                for ptype in possible_pseudod:
                    if len(loss_curves[ptype]) > 0:
                        min_len = np.min([len(c) for c in loss_curves[ptype]] + [min_len])

                for ptype in possible_pseudod:
                    # for ptype in ['originalpseudod']:
                    print(ptype, ' has ', len(loss_curves[ptype]), ' runs ')
                    if len(loss_curves[ptype]) > 0:
                        # min_len = np.min([len(c) for c in loss_curves[ptype]])
                        equalized_loss_curves = np.array([c[:min_len] for c in loss_curves[ptype]])
                        mean = np.mean(equalized_loss_curves, axis=0)
                        std = np.std(equalized_loss_curves, axis=0)
                        axs[ci, a_i].plot(mean, color=pseudod_color(ptype))
                        axs[ci, a_i].fill_between(range(len(mean)), mean - std, mean + std, alpha=0.5,
                                                  color=pseudod_color(ptype))
                axs[ci, a_i].set_title(c)
    axs[0, 0].set_xlabel('training iteration')

    plt.text(28, 6.5, 'LIF network', rotation=90, fontsize=18, ha='right')
    plt.text(28, 13, 'SHD task', rotation=90, fontsize=18, ha='right')

    legend_elements = [Line2D([0], [0], color=pseudod_color(n), lw=4, label=clean_pseudname(n))
                       for n in possible_pseudod]
    plt.legend(handles=legend_elements, loc='center left', bbox_to_anchor=(-2.15, .5))
    # plt.legend(handles=legend_elements, loc='center left', bbox_to_anchor=(1, 1.2))
    axs[-1, 0].axis('off')
    # plt.legend(loc='center left', bbox_to_anchor=(1, 0.5))

    plot_filename = r'experiments/figure1_net_task.pdf'.format(choice)
    fig.savefig(plot_filename, bbox_inches='tight')
    plt.show()



elif args.type == 'pseudod':

    df = df[df['comments'].str.contains("pseudod")]
    # df = df[df['task_name'] == 'wordptb']

    type = 'sharpn'  # dampf sharpn
    df = df[df['comments'].str.contains(type)]

    df['comments'] = df['comments'].astype(str) + '_'

    # nets = np.unique(df['net_name'])

    nets = ['SNU', 'LSNN', 'sLSTM']
    tasks = ['wordptb', 'heidelberg', 'sl_mnist']
    comments = np.unique(df['comments'])
    pseudods_names = [[p for p in c.split('_') if 'pseudo' in p][0] for c in comments]
    pseudods_values = [[p.split(':')[1] for p in c.split('_') if type in p][0] for c in comments]

    pseudods_names = np.unique(pseudods_names)
    pseudods_values = [float(i) for i in np.unique(pseudods_values)]

    fig, axs = plt.subplots(len(tasks), len(nets), gridspec_kw={'wspace': .15})
    for j, task in enumerate(tasks):

        idf = df[df['task_name'] == task]
        if task == 'wordptb':
            metric = 'val_perplexity'
            ylims = [0, 500]
        elif task == 'heidelberg':
            metric = 'val_sparse_mode_accuracy'
            ylims = [0, 90]
        elif task == 's_mnist':
            metric = 'val_sparse_mode_accuracy'
            ylims = [0, 90]
        elif task == 'sl_mnist':
            metric = 'val_sparse_mode_accuracy'
            ylims = [0, 100]
        else:
            raise NotImplementedError

        for i, net in enumerate(nets):
            # plt.figure()
            if net == 'LSNN':
                small_df = idf[idf['net_name'] == 'maLSNN']
                small_df = small_df[small_df['comments'].str.contains("embproj_nolearnv0")]
            elif net == 'SNU':
                small_df = idf[idf['net_name'] == 'maLSNN']
                small_df = small_df[small_df['comments'].str.contains("noalif")]
            elif net == 'sLSTM':
                small_df = idf[idf['net_name'] == 'spikingLSTM']
            else:
                raise NotImplementedError

            for ptype in pseudods_names:
                bpcs = []
                for pvalue in pseudods_values:
                    row = small_df[small_df['comments'].str.contains(ptype)]
                    row = row[row['comments'].str.contains(str(pvalue))]
                    # assert row.shape[0] == 1
                    try:
                        metric_value = row.at[0, metric] * (100 if 'acc' in metric else 1)
                        bpcs.append(metric_value)
                    except:
                        bpcs.append(None)

                pseudods_values, bpcs = zip(*sorted(zip(pseudods_values, bpcs)))

                axs[j, i].plot(pseudods_values, bpcs, label=clean_pseudo_name(ptype), color=pseudod_color(ptype))

            study = 'sharpness' if type == 'sharpn' else 'dampening'
            axs[0, i].set_title(net)
            axs[j, i].set_ylim(ylims)

        axs[j, 0].set_ylabel(
            '{}\n{}'.format(task.replace('s_mnist', 'sMNIST'), metric.replace('val_', '').replace('sparse_mode_', '')))
    axs[-1, 0].set_xlabel(study)

    for i in range(axs.shape[0]):
        for j in range(axs.shape[1]):
            for pos in ['right', 'left', 'bottom', 'top']:
                axs[j, i].spines[pos].set_visible(False)

            if j < axs.shape[0] - 1:
                axs[j, i].tick_params(
                    axis='x',  # changes apply to the x-axis
                    which='both',  # both major and minor ticks are affected
                    bottom=False,  # ticks along the bottom edge are off
                    top=False,  # ticks along the top edge are off
                    labelbottom=False)

            if i > 0:
                axs[j, i].tick_params(
                    axis='y',  # changes apply to the x-axis
                    which='both',  # both major and minor ticks are affected
                    right=False,  # ticks along the bottom edge are off
                    left=False,  # ticks along the top edge are off
                    labelleft=False)

    plot_filename = r'experiments/pseudods_{}.pdf'.format(study)
    fig.savefig(plot_filename, bbox_inches='tight')
    plt.show()




elif args.type == 'robustness':
    # pass
    # print(ds[:1])
    task_name = 'heidelberg'
    filename = os.path.join(EXPERIMENTS, 'robustness.json')

    if not os.path.isfile(filename):
        all_to_plot = {}
        for d in ds:
            # break
            d_path = os.path.join(EXPERIMENTS, d)
            config_path = os.path.join(d_path, '1', 'config.json')

            with open(config_path) as f:
                config = json.load(f)

            if conditions_weights(config, task_name):
                print('-----------------------------')
                print(config['task_name'])
                print(config['comments'])
                model_path = os.path.join(d_path, 'trained_models', 'train_model.h5')
                model_args = ['task_name', 'net_name', 'n_neurons', 'tau', 'input_scaling', 'n_dt_per_step',
                              'neutral_phase_length', 'reg_cost', 'lr', 'batch_size', 'stack', 'loss_name',
                              'embedding', 'skip_inout', 'spike_dropout', 'spike_dropin', 'optimizer_name',
                              'lr_schedule', 'weight_decay', 'clipnorm', 'initializer', 'comments']
                kwargs = {k: config[k] for k in model_args}

                # task definition
                maxlen = 100
                if 'maxlen:' in config['comments']:
                    maxlen = int([s for s in config['comments'].split('_') if 'maxlen:' in s][0].replace('maxlen:', ''))

                steps_per_epoch = 4  # config['steps_per_epoch']
                gen_val = Task(n_dt_per_step=config['n_dt_per_step'], batch_size=config['batch_size'],
                               steps_per_epoch=steps_per_epoch, category_coding=config['category_coding'],
                               name=config['task_name'], train_val_test='val',
                               neutral_phase_length=config['neutral_phase_length'], maxlen=maxlen)

                final_epochs = gen_val.epochs
                final_steps_per_epoch = gen_val.steps_per_epoch
                tau_adaptation = int(gen_val.in_len / 2)  # 200 800 4000
                kwargs.update(
                    {'in_len': gen_val.in_len, 'n_in': gen_val.in_dim, 'out_len': gen_val.out_len,
                     'n_out': gen_val.out_dim,
                     'tau_adaptation': tau_adaptation, 'final_epochs': gen_val.epochs,
                     'final_steps_per_epoch': gen_val.steps_per_epoch})

                train_model = build_model(**kwargs)
                w_names = [copy.deepcopy(w.name) for w in train_model.weights]

                # evaluation = train_model.evaluate(gen_val, return_dict=True)
                # print(evaluation)
                train_model.load_weights(model_path)
                # evaluation = train_model.evaluate(gen_val, return_dict=True)
                # print(evaluation)

                names = [weight.name for layer in train_model.layers for weight in layer.weights]
                rec_name = [n for n in names if 'recurrent' in n][0]
                weights = train_model.get_weights()

                original_rec_w = weights[names.index(rec_name)]
                evaluations = {}
                for n_mask in [0., .2, .4, .6, .8, 1.]:
                    mask = np.random.choice([0, 1], size=original_rec_w.shape, p=[n_mask, 1 - n_mask])
                    weights[names.index(rec_name)] = original_rec_w * mask
                    train_model.set_weights(weights)

                    evaluation = train_model.evaluate(gen_val, return_dict=True)
                    evaluations[n_mask] = evaluation

                all_to_plot[config['comments']] = evaluations

        json.dump(all_to_plot, open(filename, "w"))
    else:
        with open(filename) as f:
            all_to_plot = json.load(f)

    print(all_to_plot)
    metric = 'mode_accuracy'
    plt.figure()
    for k in all_to_plot.keys():
        evaluations = all_to_plot[k]
        p_mask = evaluations.keys()
        performances = [evaluations[m][metric] for m in p_mask]

        plt.plot(p_mask, performances, label=k)

    plt.legend()

    plot_filename = os.path.join(*['experiments', '{}_figure_robustness.png'.format(timeStructured())])
    plt.savefig(plot_filename, bbox_inches='tight')
    plt.show()



else:

    raise NotImplementedError

print('DONE')
