import os, shutil, logging, json, copy

import pandas as pd

from stablespike.neural_models.find_sparsities import reduce_model_firing_activity
from pyaromatics.keras_tools.esoteric_tasks import language_tasks
from pyaromatics.keras_tools.silence_tensorflow import silence_tf

silence_tf()

import tensorflow as tf

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

from pyaromatics.keras_tools.esoteric_callbacks.several_validations import MultipleValidationSets
from stablespike.config.config import default_config

os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
os.environ["TF_GPU_ALLOCATOR"] = "cuda_malloc_async"
os.environ["TF_CPP_VMODULE"] = "gpu_process_state=10,gpu_cudamallocasync_allocator=10"

tf.compat.v1.enable_eager_execution()

from pyaromatics.keras_tools.esoteric_initializers import esoteric_initializers_list, get_initializer
from pyaromatics.keras_tools.esoteric_callbacks import *
from pyaromatics.keras_tools.plot_tools import plot_history
from pyaromatics.stay_organized.VeryCustomSacred import CustomExperiment, ChooseGPU
from pyaromatics.stay_organized.utils import setReproducible, str2val, NumpyEncoder

from pyaromatics.keras_tools.esoteric_tasks.time_task_redirection import Task, checkTaskMeanVariance
from stablespike.visualization_tools.training_tests import Tests
from stablespike.neural_models.full_model import build_model

FILENAME = os.path.realpath(__file__)
CDIR = os.path.dirname(FILENAME)

ex = CustomExperiment('-mnl', base_dir=CDIR, seed=11)
logger = logging.getLogger('mylogger')


@ex.config
def config():
    # environment properties
    GPU = None
    seed = 41

    # task and net
    # ptb time_ae simplest_random time_ae_merge ps_mnist wiki103 wmt14 s_mnist xor small_s_mnist
    # wordptb sl_mnist heidelberg
    task_name = 'wordptb'

    # test configuration
    epochs = 1
    steps_per_epoch = 1
    batch_size = 2
    stack = '3:3:3'
    n_neurons = None

    # net
    # LSNN maLSNN spikingLSTM
    net_name = 'maLSNN'

    # zero_mean_isotropic zero_mean learned positional normal onehot zero_mean_normal
    embedding = 'learned:None:None:{}'.format(n_neurons) if task_name in language_tasks else False

    comments = '7_embproj_noalif_nogradreset_dropout:.3_timerepeat:2_mlminputs_conditionIII'

    # optimizer properties
    lr = None  # 7e-4
    optimizer_name = 'AdamW'  # AdaBelief AdamW SWAAdaBelief
    lr_schedule = ''  # 'warmup_cosine_restarts'
    weight_decay_prop_lr = None
    weight_decay = .01 if not 'mnist' in task_name else 0.  # weight_decay_prop_lr * lr
    clipnorm = 1.  # not 1., to avoid NaN in the embedding, only ptb though

    loss_name = 'sparse_categorical_crossentropy'  # categorical_crossentropy categorical_focal_loss contrastive_loss
    initializer = 'glorot_uniform'  # uniform glorot_uniform orthogonal glorot_normal NoZeroGlorot

    continue_training = ''
    save_model = False

    # 22h=79200 s, 21h=75600 s, 20h=72000 s, 12h = 43200 s, 6h = 21600 s, 72h = 259200
    stop_time = 21600


@ex.capture
@ex.automain
def main(epochs, steps_per_epoch, batch_size, GPU, task_name, comments,
         continue_training, save_model, seed, net_name, n_neurons, lr, stack, loss_name, embedding, optimizer_name,
         lr_schedule, weight_decay, clipnorm, initializer, stop_time, _log):
    stack, batch_size, embedding, n_neurons, lr = default_config(stack, batch_size, embedding, n_neurons, lr, task_name,
                                                                 net_name)
    sLSTM_factor = 2 / 3 if task_name == 'wordptb' else 1 / 3
    n_neurons = n_neurons if not 'LSTM' in net_name else int(n_neurons * sLSTM_factor)

    exp_dir = os.path.join(*[CDIR, ex.observers[0].basedir])
    comments += '_**folder:' + exp_dir + '**_'

    images_dir = os.path.join(*[exp_dir, 'images'])
    other_dir = os.path.join(*[exp_dir, 'other_outputs'])
    models_dir = os.path.join(*[exp_dir, 'trained_models'])

    full_mean, full_var = checkTaskMeanVariance(task_name)
    print(comments)
    comments = comments + '_taskmean:{}_taskvar:{}'.format(full_mean, full_var)
    print(comments)

    ChooseGPU(GPU)
    setReproducible(seed)

    shutil.copytree(os.path.join(CDIR, 'neural_models'), other_dir + '/neural_models')
    shutil.copyfile(FILENAME, other_dir + '/' + os.path.split(FILENAME)[-1])

    timerepeat = str2val(comments, 'timerepeat', int, default=1)
    maxlen = str2val(comments, 'maxlen', int, default=100)
    comments = str2val(comments, 'maxlen', int, default=maxlen, replace=maxlen)
    comments += '_batchsize:' + str(batch_size)

    # task definition
    gen_train = Task(timerepeat=timerepeat, epochs=epochs, batch_size=batch_size, steps_per_epoch=steps_per_epoch,
                     name=task_name, train_val_test='train', maxlen=maxlen, comments=comments)
    gen_val = Task(timerepeat=timerepeat, batch_size=batch_size, steps_per_epoch=steps_per_epoch,
                   name=task_name, train_val_test='val', maxlen=maxlen, comments=comments)
    gen_val2 = Task(timerepeat=timerepeat, batch_size=batch_size, steps_per_epoch=steps_per_epoch,
                    name=task_name, train_val_test='val', maxlen=maxlen, comments=comments)
    gen_test = Task(timerepeat=timerepeat, batch_size=batch_size, steps_per_epoch=steps_per_epoch,
                    name=task_name, train_val_test='test', maxlen=maxlen, comments=comments)

    final_epochs = gen_train.epochs
    final_steps_per_epoch = gen_train.steps_per_epoch
    # tau_adaptation = int(gen_train.in_len / 2)  # 200 800 4000

    if initializer in esoteric_initializers_list:
        initializer = get_initializer(initializer_name=initializer)

    model_args = dict(task_name=task_name, net_name=net_name, n_neurons=n_neurons, lr=lr, stack=stack,
                      loss_name=loss_name, embedding=embedding, optimizer_name=optimizer_name, lr_schedule=lr_schedule,
                      weight_decay=weight_decay, clipnorm=clipnorm, initializer=initializer, comments=comments,
                      in_len=gen_train.in_len, n_in=gen_train.in_dim, out_len=gen_train.out_len,
                      n_out=gen_train.out_dim, vocab_size=gen_train.vocab_size,
                      final_epochs=gen_train.epochs)
    train_model = build_model(**model_args)

    results = {}
    # this block is only necessary when I'm continuing training a previous model
    if 'continue_202' in continue_training:
        print(continue_training)
        path_exp = os.path.join(CDIR, 'experiments', continue_training.replace('continue_', ''))
        path_model = os.path.join(path_exp, 'trained_models', 'train_model.h5')
        train_model.load_weights(path_model)

        old_results = os.path.join(path_exp, 'other_outputs', 'results.json')

        with open(old_results) as f:
            old_data = json.load(f)

        results['accumulated_epochs'] = old_data['accumulated_epochs']  # + final_epochs
    else:
        results['accumulated_epochs'] = 0  # final_epochs

    train_model.summary()

    history_path = other_dir + '/log.csv'

    checkpoint_filepath = os.path.join(models_dir, 'checkpoint')
    callbacks = [
        LearningRateLogger(),
        VariablesLogger(variables_to_log=['switch']),
        TimeStopping(stop_time, 1),  # 22h=79200 s, 21h=75600 s, 20h=72000 s, 12h = 43200 s, 6h = 21600 s, 72h = 259200
        tf.keras.callbacks.ModelCheckpoint(
            filepath=checkpoint_filepath, save_weights_only=True, monitor='val_loss', mode='min', save_best_only=True
        ),
        MultipleValidationSets({'v': gen_val2, 't': gen_test}, verbose=0),
        CSVLogger(history_path),
        tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=10, restore_best_weights=True)
    ]

    if 'annealing' in comments:
        annealing_schedule = str2val(comments, 'annealing', str, default='la')
        callbacks.append(
            AnnealingCallback(
                epochs=final_epochs, variables_to_anneal=['switch'], annealing_schedule=annealing_schedule,
            )
        )

    if 'adjfi' in comments:
        # Pretrain biases to achieve desired initial firing rates for Figure 3.
        new_model_args = copy.deepcopy(model_args)
        new_model_args['comments'] = new_model_args['comments'].replace('adjff:', '')

        tf.keras.backend.clear_session()
        del train_model

        train_model = build_model(**new_model_args)

        target_firing_rate = str2val(comments, 'adjfi', float, default=.1)
        adjfi_epochs = 2 if 'test' in comments else 15
        sparsification_results = reduce_model_firing_activity(
            train_model, target_firing_rate, gen_train, epochs=adjfi_epochs
        )
        results.update(sparsification_results)
        weights = train_model.get_weights()
        tf.keras.backend.clear_session()
        del train_model

        train_model = build_model(**model_args)
        train_model.set_weights(weights)

    if 'condition' in comments:
        for layer in train_model.layers:
            if ('lsnn' in net_name.lower() or 'lif' in net_name.lower()) and 'encoder' in layer.name.lower():
                for k in layer.cell.lsnn_results.keys():
                    results.update({k: layer.cell.lsnn_results[k].numpy().mean()})

    train_model.fit(
        gen_train, batch_size=batch_size, validation_data=gen_val, epochs=final_epochs,
        steps_per_epoch=steps_per_epoch,
        callbacks=callbacks
    )

    actual_epochs = 0
    if final_epochs > 0:
        try:
            train_model.load_weights(checkpoint_filepath)
        except Exception as e:
            print(e)
            print('No checkpoint found!')
        history_df = pd.read_csv(history_path)

        actual_epochs = history_df['epoch'].iloc[-1] + 1
        results['accumulated_epochs'] = str(int(results['accumulated_epochs']) + int(actual_epochs))

        history_dict = {k: history_df[k].tolist() for k in history_df.columns.tolist()}
        json_filename = os.path.join(other_dir, 'history.json')
        history_jsonable = {k: np.array(v).astype(float).tolist() for k, v in history_dict.items()}
        json.dump(history_jsonable, open(json_filename, "w"))

        history_keys = history_df.columns.tolist()
        lengh_keys = 6
        no_vals_keys = [k for k in history_keys if not k.startswith('val_')]
        all_chunks = [no_vals_keys[x:x + lengh_keys] for x in range(0, len(no_vals_keys), lengh_keys)]
        for i, subkeys in enumerate(all_chunks):
            history_dict = {k: history_df[k].tolist() for k in subkeys}
            history_dict.update(
                {'val_' + k: history_df['val_' + k].tolist() for k in subkeys if 'val_' + k in history_keys}
            )
            plot_filename = os.path.join(images_dir, f'history_{i}.png')
            plot_history(histories=history_dict, plot_filename=plot_filename, epochs=final_epochs)

        removable_checkpoints = sorted([d for d in os.listdir(models_dir) if 'checkpoint' in d])
        for d in removable_checkpoints: os.remove(os.path.join(models_dir, d))

    print('Fitting done!')
    if save_model:
        train_model_path = os.path.join(models_dir, 'train_model.h5')
        train_model.save(train_model_path)
        print('Model saved!')

    # plots after training
    test_results = Tests(task_name, gen_test, train_model, images_dir, save_pickle=False, model_args=model_args,
                         grad_tests=False)
    results.update(test_results)

    evaluation = train_model.evaluate(gen_test, return_dict=True, verbose=True)
    for k in evaluation.keys():
        results['test_' + k] = evaluation[k]

    results['n_params'] = train_model.count_params()
    results['final_epochs'] = str(actual_epochs)
    results['final_steps_per_epoch'] = final_steps_per_epoch
    results['batch_size'] = batch_size
    results['lr'] = lr
    results['n_neurons'] = n_neurons
    results['stack'] = stack
    results['embedding'] = embedding
    results['comments'] = comments

    results_filename = os.path.join(other_dir, 'results.json')
    json.dump(results, open(results_filename, "w"), cls=NumpyEncoder)

    string_result = json.dumps(results, indent=4, cls=NumpyEncoder)
    print(string_result)
    path = os.path.join(other_dir, 'results.txt')
    with open(path, "w") as f:
        f.write(string_result)

    print('DONE')
