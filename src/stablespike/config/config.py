from pyaromatics.keras_tools.esoteric_tasks import language_tasks


def default_config(stack, batch_size, embedding, n_neurons, lr, task_name, net_name, setting='LIF'):
    assert setting in ['LIF', 'LSC']

    if 'lru' in net_name:
        if n_neurons is None:
            n_neurons = 128
            embedding = 'learned:None:None:{}'.format(n_neurons)
        if batch_size is None:
            batch_size = 8
        if lr is None:
            lr = 4e-3


    if n_neurons is None:
        if isinstance(stack, str) and ':' in stack:
            n_neurons = int(stack.split(':')[-1])

        elif task_name in language_tasks:
            n_neurons = 1300
        elif task_name in ['heidelberg', 'lca']:
            n_neurons = 256
        elif 'mnist' in task_name:
            n_neurons = 128
        else:
            raise NotImplementedError

    if lr is None:
        if setting == 'LIF':
            if task_name in language_tasks:
                lr = 3.16e-5
            elif task_name in ['heidelberg', 'lca']:
                lr = 3.16e-4
            elif 'mnist' in task_name:
                lr = 3.16e-4
            else:
                raise NotImplementedError

        elif setting == 'LSC':
            if net_name in ['maLSNN', 'maLSNNb', 'maLSNNc']:
                lr = 1e-3
            elif net_name in [
                'LSTM', 'GRU', 'indrnn', 'LMU', 'rsimplernn', 'ssimplernn', 'reslru', 'lru', 'reslruffn', 'lruffn'
            ]:

                if task_name in language_tasks:
                    lr = 3.16e-4
                elif task_name in ['heidelberg', 'lca']:
                    lr = 1e-3
                elif 'mnist' in task_name:
                    lr = 1e-2
                else:
                    raise NotImplementedError

            else:
                raise NotImplementedError

        else:
            raise NotImplementedError

    if batch_size is None:
        if task_name in language_tasks:
            batch_size = 32
        elif task_name in ['heidelberg', 'lca']:
            batch_size = 128 if setting == 'LIF' else 100
            if stack in [3, 5, 7]:
                batch_size = 32
        elif 'mnist' in task_name:
            batch_size = 256
        else:
            raise NotImplementedError

    if stack is None:
        if 'mnist' in task_name or task_name in ['heidelberg', 'lca']:
            stack = 2
        elif task_name in language_tasks:
            stack = '1700:300' if setting == 'LIF' else '1300:300'
            embedding = 'learned:None:None:300'
            if net_name in ['LSTM']:
                stack = '700:300' if setting == 'LIF' else '500:300'
            elif net_name == 'GRU':
                stack = '625:300'
            elif net_name == 'indrnn':
                stack = '4250:300'

        else:
            raise NotImplementedError

    elif isinstance(stack, int) and not 'lru' in net_name and n_neurons is None:

        if task_name in ['wordptb']:
            base_neurons = 1700 if setting == 'LIF' else 1300
            embedding = 'learned:None:None:300'
            if net_name in ['LSTM']:
                base_neurons = 700 if setting == 'LIF' else 500
            elif net_name == 'GRU':
                base_neurons = 625

            stack = ':'.join([f'{base_neurons}:{base_neurons//5}'] * (stack//2)) + ':300'


    elif isinstance(stack, int) and not 'lru' in net_name and not n_neurons is None:
        embedding = f'learned:None:None:{n_neurons}'
        stack = ':'.join([f'{n_neurons}'] * stack)


    if embedding == None:
        embedding = False

    if task_name == 'heidelberg':
        sLSTM_factor = .37  # 1 / 3
        GRU_factor = .46  # 1 / 3
        indrnn_factor = 1.38  # 1 / 3
        srnn_factor = 1

    elif task_name == 'sl_mnist':
        sLSTM_factor = 1 / 3
        GRU_factor = .42
        indrnn_factor = 1.25  # 1 / 3
        srnn_factor = 1

    else:
        sLSTM_factor = 1 / 3
        GRU_factor = .42
        indrnn_factor = .46  # 1 / 3
        srnn_factor = 1

    n_neurons = n_neurons if not 'LSTM' in net_name else int(n_neurons * sLSTM_factor)
    n_neurons = n_neurons if not 'GRU' in net_name else int(n_neurons * GRU_factor)
    n_neurons = n_neurons if not 'indrnn' in net_name else int(n_neurons * indrnn_factor)
    n_neurons = n_neurons if not net_name in ['rsimplernn', 'ssimplernn'] else int(srnn_factor * n_neurons)

    return stack, batch_size, embedding, n_neurons, lr
