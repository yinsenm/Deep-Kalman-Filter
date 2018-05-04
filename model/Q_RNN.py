import tensorflow as tf
import numpy as np

from tensorflow.contrib.distributions import MultivariateNormalFullCovariance

from model.Network import Network


class Q_RNN(object):

    def __init__(self, num_inputs, num_units, num_layers, time_step, size, scope):

        self.num_inputs = num_inputs
        self.num_units = num_units
        self.num_layers = num_layers
        self.time_step = time_step
        self.size = size
        self.scope = scope
        self.init = tf.random_normal_initializer()
        self.activation = tf.nn.tanh

        self.proposal = Network(num_inputs=self.num_inputs,
                                num_units=self.num_units,
                                num_layers=self.num_layers,
                                num_levels=self.time_step,
                                scope_r="recognition")

    def build_network(self, status):
        # assert the data's integrity
        assert (status.shape[0] == self.time_step), "Input dimension doesn't match with the time step"

        # get parameters from the given input(status)
        param_stack = self.proposal.get_latent_samples(status=status)
        list = []
        with tf.variable_scope(name_or_scope=self.scope, reuse=tf.AUTO_REUSE):
            # iterate over the time step
            # when t == 0
            time = 0
            [q_mean, q_cov] = param_stack.pop()
            samples = q_mean + tf.matmul(tf.random_normal(shape=(1, self.num_units)), q_cov)
            # transition
            p_mean = tf.zeros(shape=(1, self.num_units))
            p_cov = tf.eye(num_rows=self.num_units)
            # emission
            h = tf.layers.dense(inputs=samples,
                                units=self.num_units,
                                activation=self.activation,
                                kernel_initializer=self.init,
                                name="emission")
            mu = tf.layers.dense(inputs=h,
                                 units=self.num_units,
                                 kernel_initializer=self.init,
                                 name="mu")
            logd = tf.layers.dense(inputs=h,
                                   units=self.num_units,
                                   kernel_initializer=self.init,
                                   name="logd")
            cov = tf.diag(tf.exp(logd[0]))
            x_dist = MultivariateNormalFullCovariance(loc=mu, covariance_matrix=cov)
            x = tf.reshape(tensor=status[0], shape=(1, self.num_units))
            x_prob = x_dist.prob(value=x)
            list.append([q_mean, q_cov, p_mean, p_cov, x_prob, samples])

            while len(param_stack) != 0:
                time = time + 1
                var = tf.trainable_variables(scope=self.scope)
                print("Current number of weights in {}-th generative network: {}".format(time, len(var)))
                [q_mean, q_cov] = param_stack.pop()
                # transition
                for i in range(self.num_layers):
                    p_mean = tf.layers.dense(inputs=samples,
                                             units=self.num_units,
                                             use_bias=False,
                                             kernel_initializer=self.init,
                                             name="dense" + str(i))

                samples = q_mean + tf.matmul(tf.random_normal(shape=(1, self.num_units)), q_cov)
                p_cov = tf.diag(tf.exp(tf.random_normal(shape=(1, self.num_units)))[0])
                # emission
                h = tf.layers.dense(inputs=samples,
                                    units=self.num_units,
                                    activation=self.activation,
                                    kernel_initializer=self.init,
                                    name="emission")
                mu = tf.layers.dense(inputs=h,
                                     units=self.num_units,
                                     kernel_initializer=self.init,
                                     name="mu")
                logd = tf.layers.dense(inputs=h,
                                       units=self.num_units,
                                       kernel_initializer=self.init,
                                       name="logd")
                cov = tf.diag(tf.exp(logd[0]))
                x_dist = MultivariateNormalFullCovariance(loc=mu, covariance_matrix=cov)
                x = tf.reshape(tensor=status[0], shape=(1, self.num_units))
                x_prob = x_dist.prob(value=x)

                list.append([q_mean, q_cov, p_mean, p_cov, x_prob, samples])

        return list

    def compute_loss(self, param_list):
        # iterate over time
        sum = 0.0
        for t in range(len(param_list)):
            # transition
            [q_mean, q_cov, p_mean, p_cov, x_prob, samples] = param_list.pop()
            kl_div = self.get_divergence(mean1=q_mean, mean2=p_mean, cov1=q_cov, cov2=p_cov)
            sum = sum - kl_div
            # emission
            log_prob = tf.log(x_prob)
            sum = sum + log_prob
            print("Time {} -> Sum: {}, KL-divergence: {}, log_prob: {}".format(t, sum, kl_div, log_prob))
        param_list.clear()
        return sum

    def get_trainable(self):
        return tf.trainable_variables(scope=self.scope)

    @staticmethod
    def get_divergence(mean1, mean2, cov1, cov2):
        div = 0.0
        div = div + tf.log(tf.linalg.det(cov2) / tf.linalg.det(cov1))
        div = div - tf.cast(x=cov1.shape[0], dtype=tf.float32)
        div = div + tf.trace(tf.matmul(tf.matrix_inverse(cov2), cov1))
        diff = mean2 - mean1
        div = div + tf.matmul(diff, tf.matmul(tf.matrix_inverse(cov2), tf.transpose(diff)))
        return 0.5 * div