from pyaromatics.keras_tools.esoteric_initializers import PluriInitializerI
from pyaromatics.keras_tools.esoteric_layers import SurrogatedStep
import tensorflow as tf
import numpy as np
import os

# from pyaromatics.keras_tools.esoteric_layers.surrogated_step import *
from pyaromatics.stay_organized.utils import str2val
from stablespike.neural_models.optimize_dampening_sharpness import optimize_dampening, optimize_sharpness, \
    optimize_tail


def variance_distance(tensor_1, tensor_2):
    var_1 = tf.math.reduce_variance(tensor_1, axis=-1)
    var_2 = tf.math.reduce_variance(tensor_2, axis=-1)
    return tf.reduce_mean(tf.abs(var_1 - var_2))


class baseLSNN(tf.keras.layers.Layer):
    """
    LSNN
    """

    def get_config(self):
        base_config = super().get_config()
        return dict(list(base_config.items()) + list(self.init_args.items()))

    def __init__(self, num_neurons=None, tau=20., beta=1.8, tau_adaptation=20,
                 dampening_factor=1., ref_period=-1, thr=.01, inh_exc=1.,
                 n_regular=None, internal_current=0, initializer='orthogonal',
                 config=None, v_eq=0,
                 **kwargs):
        super().__init__(**kwargs)

        ref_period = str2val(config, 'refp', float, default=ref_period)
        if n_regular == None: n_regular = 0  # int(num_neurons / 3)
        self.init_args = dict(
            num_neurons=num_neurons, tau=tau, tau_adaptation=tau_adaptation,
            ref_period=ref_period, n_regular=n_regular, thr=thr,
            dampening_factor=dampening_factor, beta=beta, inh_exc=inh_exc,
            v_eq=v_eq, internal_current=internal_current, initializer=initializer, config=config
        )
        self.__dict__.update(self.init_args)

        if self.ref_period > 0:
            self.state_size = [num_neurons, num_neurons, num_neurons]
        else:
            self.state_size = [num_neurons, num_neurons]

        if not 'reoldspike' in self.config:
            self.state_size.append(num_neurons)

        self.mask = tf.ones((self.num_neurons, self.num_neurons)) - tf.eye(self.num_neurons)
        if 'withrecdiag' in self.config:
            self.mask = tf.ones((self.num_neurons, self.num_neurons))

        self.lsnn_results = {}

    def decay_v(self):
        return tf.exp(-1 / self.tau)

    def build(self, input_shape):

        n_in = input_shape[-1]
        n_rec = self.num_neurons

        stacki = str2val(self.config, 'stacki', int, default=0)
        decay_v = self.decay_v()
        dampening = self.dampening_factor
        sharpness = 1.

        if 'conditionIV' in self.config or 'conditionIII' in self.config:
            exp = str2val(self.config, 'folder', str, default='', split_symbol='**')
            dpath = os.path.join(exp, 'trained_models', 'dampening_stacki{}.npy'.format(stacki - 1))
            dampening_in = 0 if stacki == 0 or not 'deltain' in self.config else np.load(dpath)

            spath = os.path.join(exp, 'trained_models', 'sharpness_stacki{}.npy'.format(stacki - 1))
            sharpness_in = 0 if stacki == 0 or not 'deltain' in self.config else np.load(spath)

        input_init = self.initializer
        recurrent_init = self.initializer
        mean_rec = 0
        if '_conditionI_' in self.config:
            if not 'multreset' in self.config:
                mean_rec = 1 / (n_rec - 1) * (3 - 2 * decay_v) * self.thr
            elif 'multreset1' in self.config:
                mean_rec = 2 / (n_rec - 1) * (1 - decay_v) * self.thr
            elif 'multreset2' in self.config:
                mean_rec = 1 / (n_rec - 1) * (2 - decay_v) * self.thr
            else:
                mean_rec = 2 / (n_rec - 1) * (1 - decay_v) * self.thr
            recurrent_init = PluriInitializerI(mean=mean_rec)

        self.input_weights = self.add_weight(shape=(n_in, n_rec), initializer=input_init, name='input_weights')

        if '_conditionII_' in self.config:
            assert 'taskmean' in self.config and 'taskvar' in self.config
            if stacki == 0:
                input_mean = str2val(self.config, 'taskmean', float, default=None)
                input_var = str2val(self.config, 'taskvar', float, default=None)
            else:
                input_mean, input_var = 1 / 2, 1 / 4

            var_rec = (input_var + input_mean ** 2) * tf.math.reduce_variance(self.input_weights) \
                      * n_in / (n_rec - 1) - mean_rec ** 2 / 2

            recurrent_init = PluriInitializerI(mean=mean_rec, scale=tf.math.sqrt(var_rec))

        if 'wrecm' in self.config:
            wrecm = str2val(self.config, f'wrecm{stacki}', float, default=0)
            recurrent_init = PluriInitializerI(mean=wrecm)

        self.recurrent_weights = self.add_weight(shape=(n_rec, n_rec), initializer=recurrent_init,
                                                 name='recurrent_weights')

        if 'conditionIII' in self.config:
            od_type = str2val(self.config, 'conditionIII', str, default='c')
            thr = self.thr if not 'multreset' in self.config else 0
            dampening = optimize_dampening(self.recurrent_weights, thr=thr, decay=decay_v, w_in=self.input_weights,
                                           dampening_in=dampening_in, od_type=od_type)
            self.lsnn_results.update({f'dampening_{self.name}': dampening})

        if 'conditionIV' in self.config and not 'optimizetail' in self.config:
            assert 'exponentialpseudod' in self.config, \
                "Condition IV has been coded only for exponential SG !"

            os_type = str2val(self.config, 'conditionIV', str, default='b')
            sharpness = optimize_sharpness(w_rec=self.recurrent_weights, w_in=self.input_weights, decay=decay_v,
                                           thr=self.thr, dampening=dampening,
                                           dampening_in=dampening_in,
                                           sharpness_in=sharpness_in, os_type=os_type, config=self.config)
            self.lsnn_results.update({f'sharpness_{self.name}': sharpness})

        if 'conditionIV' in self.config and 'optimizetail' in self.config:
            assert 'ntailpseudod' in self.config, \
                "Condition IV optimizetail has been coded only for ntailpseudod SG !"

            tail = optimize_tail(
                self.recurrent_weights, self.input_weights, decay_v, self.thr, dampening, sharpness_in, dampening_in
            )
            self.config = str2val(self.config, 'tailvalue', replace=np.mean(tail))
            self.lsnn_results.update({f'tail_{self.name}': sharpness})

        # self.inh_exc = tf.ones(self.num_neurons)
        self._beta = tf.concat([tf.zeros(self.n_regular), tf.ones(n_rec - self.n_regular) * self.beta], axis=0)

        if 'conditionIV' in self.config or 'conditionIII' in self.config:
            dpath = os.path.join(exp, 'trained_models', 'dampening_stacki{}.npy'.format(stacki))
            np.save(dpath, dampening)
            spath = os.path.join(exp, 'trained_models', 'sharpness_stacki{}.npy'.format(stacki))
            np.save(spath, sharpness)

        self.spike_type = SurrogatedStep(config=self.config, dampening=dampening, sharpness=sharpness)

        if 'adjff' in self.config:
            self.loss_switch = self.add_weight(
                name=f'switch_{stacki}_{self.name}', shape=(), initializer=tf.keras.initializers.Constant(1.),
                trainable=False
            )

        self.built = True
        super().build(input_shape)

    def recurrent_transform(self):
        return self.mask * self.recurrent_weights

    def beta_transform(self):
        return self._beta

    def current_mod(self, i_in):
        return i_in

    def refract(self, z, last_spike_distance):
        new_last_spike_distance = last_spike_distance
        if self.ref_period > 0:
            spike_locations = tf.cast(tf.math.not_equal(z, 0), tf.float32)
            non_refractory_neurons = tf.cast(last_spike_distance >= self.ref_period, tf.float32)
            z = non_refractory_neurons * z
            new_last_spike_distance = (last_spike_distance + 1) * (1 - spike_locations)
        return z, new_last_spike_distance

    def spike(self, new_v, thr, *args):
        v_sc = (new_v - thr) / thr if 'vt/t' in self.config else (new_v - thr)

        z = self.spike_type(v_sc)
        return z, v_sc

    def currents_composition(self, inputs, old_spike):

        input_current = inputs @ self.input_weights
        rec_current = old_spike @ self.recurrent_transform()

        self.add_metric(variance_distance(input_current, rec_current),
                        aggregation='mean', name='curr_dis_' + self.name)
        self.add_metric(tf.math.reduce_variance(input_current),
                        aggregation='mean', name='var_in_' + self.name)
        self.add_metric(tf.math.reduce_variance(rec_current),
                        aggregation='mean', name='var_rec_' + self.name)

        i_in = input_current + rec_current + self.internal_current

        return i_in

    def threshold_dynamic(self, old_a, old_z):
        decay_a = tf.exp(-1 / self.tau_adaptation)

        if not 'noalif' in self.config:
            new_a = decay_a * old_a + (1 - decay_a) * old_z
            athr = self.thr + new_a * self.beta_transform()

        else:
            # new_a = decay_a * old_a
            new_a = old_a
            athr = self.thr + old_a * 0

        return athr, new_a

    def voltage_dynamic(self, old_v, i_in, old_z):

        if not 'newreset' in self.config:
            i_reset = - self.athr * old_z
        else:
            i_reset = 0

        if 'noreset' in self.config:
            i_reset = 0

        if 'nogradreset':
            old_z = tf.stop_gradient(old_z)
            i_reset = tf.stop_gradient(i_reset)

        decay_v = self.decay_v()
        if 'snudecay' in self.config:
            new_v = .6 * old_v * (1 - old_z) + self.current_mod(i_in)

        elif 'lsnndecay' in self.config:
            new_v = decay_v * old_v + (1 - decay_v) * self.current_mod(i_in) + i_reset

        elif 'multreset1' in self.config:
            new_v = (decay_v * old_v + self.current_mod(i_in)) * (1 - old_z)

        elif 'multreset2' in self.config:
            new_v = decay_v * old_v * (1 - old_z) + self.current_mod(i_in)

        elif 'conductanceinput' in self.config:
            new_v = decay_v * old_v * (1 - old_z)
            new_v = new_v * self.current_mod(i_in)
        else:
            new_v = decay_v * old_v + self.current_mod(i_in) + i_reset

        return new_v

    def call(self, inputs, states, training=None):
        if not training is None:
            tf.keras.backend.set_learning_phase(training)

        if not 'reoldspike' in self.config:
            old_z = states[0]
            old_v = states[1]
            old_a = states[2]
        else:
            old_v = states[0]
            old_a = states[1]
            old_z = self.spike_type(old_v - self.thr - old_a * self.beta_transform())

        if self.ref_period > 0:
            last_spike_distance = states[3]
        else:
            last_spike_distance = None

        i_in = self.currents_composition(inputs, old_z)

        self.athr, new_a = self.threshold_dynamic(old_a, old_z)
        new_v = self.voltage_dynamic(old_v, i_in, old_z)

        z, v_sc = self.spike(new_v, self.athr, last_spike_distance, old_v, old_a, new_a)

        # refractoriness
        z, new_last_spike_distance = self.refract(z, last_spike_distance)

        fr = tf.reduce_mean(z)
        self.add_metric(fr, aggregation='mean', name='firing_rate_' + self.name)

        if 'adjff' in self.config:
            target_firing_rate = str2val(self.config, 'adjff', float, default=.1)

            loss = tf.square(tf.reduce_mean(z) - target_firing_rate)

            self.add_loss(self.loss_switch * loss)
            self.add_metric(self.loss_switch * loss, name='adjff', aggregation='mean')

        output, new_state = self.prepare_outputs(new_v, old_v, z, old_z, new_a, old_a, new_last_spike_distance,
                                                 last_spike_distance, self.athr, v_sc)
        return output, new_state

    def prepare_outputs(self, new_v, old_v, z, old_z, new_a, old_a, new_last_spike_distance, last_spike_distance, thr,
                        v_sc):

        output = [z, new_v, thr, v_sc]
        if self.ref_period > 0:
            new_state = [z, new_v, new_a, new_last_spike_distance]
        elif 'reoldspike' in self.config:
            new_state = [new_v, new_a]
        else:
            new_state = [z, new_v, new_a]

        return output, new_state


LSNN = baseLSNN


class aLSNN(baseLSNN):
    """
    LSNN where all parameters can be learned
    """

    def build(self, input_shape):
        n_input = input_shape[-1]

        if not 'noalif' in self.config:
            parameter2trainable = {k: v for k, v in self.__dict__.items()
                                   if k in ['tau_adaptation', 'thr', 'beta', 'tau']}
        else:
            parameter2trainable = {k: v for k, v in self.__dict__.items()
                                   if k in ['tau', 'thr']}
        for k, p in parameter2trainable.items():
            if k in ['tau', 'tau_adaptation', 'thr', 'dampening_factor', 'beta']:
                initializer = tf.keras.initializers.TruncatedNormal(mean=p, stddev=3 * p / 7)
                # initializer = tf.keras.initializers.TruncatedNormal(mean=p, stddev=.1 * p / 7)
            else:
                initializer = tf.keras.initializers.RandomNormal(stddev=1. / tf.sqrt(n_input))

            if k == 'beta' and 'gaussbeta' in self.config:
                initializer = tf.keras.initializers.RandomNormal(stddev=p / tf.sqrt(tf.cast(n_input, tf.float32)))

            p = self.add_weight(shape=(self.num_neurons,), initializer=initializer, name=k, trainable=True)
            self.__dict__.update({k: p})

        if '_learnv0' in self.config or 'v0m' in self.config:
            stacki = str2val(self.config, 'stacki', int, default=0)
            v0m = str2val(self.config, f'v0m{stacki}', float, default=0)
            initializer = tf.keras.initializers.RandomNormal(mean=v0m)
            self.internal_current = self.add_weight(shape=(self.num_neurons,), initializer=initializer,
                                                    name='internal_current', trainable=True)

        super().build(input_shape)

        self._beta = self.beta


class maLSNN(aLSNN):
    """
    multiplicative gaussian noise aLSNN
    The idea is to have a different type of noise in the LSNN and the unit to learn to control it
    """

    def __init__(self, *args, **kwargs):
        self.rho = None

        if 'noiserho:' in kwargs['config']:
            if 'noiserho:learned' in kwargs['config']:
                pass

            elif 'noiserho:none' in kwargs['config']:
                self.rho = None

            elif 'noiserho:gaussian' in kwargs['config']:
                self.rho = tf.random.normal((kwargs['num_neurons'],)).numpy().tolist()

            else:
                self.rho = float([i.replace('noiserho:', '')
                                  for i in kwargs['config'].split('_') if 'noiserho:' in i][0])

        super().__init__(*args, **kwargs)

    def build(self, input_shape):
        n_input = tf.cast(input_shape[-1], tf.float32)
        initializer = tf.keras.initializers.RandomNormal(stddev=1. / tf.sqrt(n_input))
        if 'veqconductance' in self.config:
            self.v_eq = self.add_weight(shape=(self.num_neurons,), initializer=initializer, name='v_eq')

        if 'noiserho:learned' in self.config:
            self.rho = self.add_weight(shape=(self.num_neurons,), initializer=initializer, name='rho')

        elif self.rho == None:
            pass

        elif hasattr(self, 'rho'):
            self.rho = self.add_weight(shape=(self.num_neurons,), initializer=tf.constant_initializer(self.rho),
                                       name='rho', trainable=False)
        else:
            self.rho = None

        if not self.rho is None:
            if not 'rhostd' in self.config:
                self.n_std = self.add_weight(shape=(self.num_neurons,), initializer=initializer, name='n_std')
            elif 'frhostd' in self.config:
                import numpy as np
                self.n_std = self.add_weight(
                    shape=(self.num_neurons,),
                    initializer=tf.constant_initializer(np.random.choice([-.01, .01], self.num_neurons)), name='n_std'
                )
            else:
                self.n_std = self.add_weight(
                    shape=(self.num_neurons,),
                    initializer=tf.constant_initializer(.01), name='n_std')

        super().build(input_shape)

    def spike(self, new_v, thr, *args):
        is_train = tf.cast(tf.keras.backend.learning_phase(), tf.float32)

        if 'thrrho' in self.config:
            in_rho = tf.abs(new_v - thr)
        else:
            in_rho = tf.abs(new_v)

        if not self.rho is None:
            noise_part = tf.pow(in_rho, tf.convert_to_tensor(self.rho) + 1) \
                         * is_train * self.n_std * tf.random.normal(new_v.shape, mean=0.0)
        else:
            noise_part = 0

        new_v = new_v + noise_part
        v_sc = (new_v - thr) / thr if 'vt/t' in self.config else (new_v - thr)

        z = self.spike_type(v_sc)
        z.set_shape(v_sc.get_shape())
        return z, v_sc


class maLSNNb(maLSNN):
    def __init__(self, *args, **kwargs):
        kwargs['config'] = kwargs['config'] + '_gaussbeta'
        super().__init__(*args, **kwargs)


class maLIF(maLSNN):
    def __init__(self, *args, **kwargs):
        kwargs['config'] = kwargs['config'] + '_noalif'
        super().__init__(*args, **kwargs)
