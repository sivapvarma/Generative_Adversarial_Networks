"""
models.py: Definitions for generator and discriminator convnets.
"""

import tensorflow as tf


# commonly used stride settings for 2D convolutions
STRIDE_1 = [1, 1, 1, 1]
STRIDE_2 = [1, 2, 2, 1]


def _bn(bottom, is_train):
    """
        Creates a batch normalization op.
        Meant to be invoked from other layer operations.
    """

    # assume inference by default
    if is_train is None:
        is_train = tf.constant(False, dtype="bool", name="is_train")

    # create scale and shift variables
    bn_shape = bottom.get_shape()[-1]
    shift = tf.get_variable("beta", shape=bn_shape,
                            initializer=tf.constant_initializer(0.0))
    scale = tf.get_variable("gamma", shape=bn_shape,
                            initializer=tf.constant_initializer(1.0))

    # compute mean and variance
    bn_axes = list(range(len(bottom.get_shape()) - 1))
    (mu, var) = tf.nn.moments(bottom, bn_axes)

    # batch normalization ops
    ema = tf.train.ExponentialMovingAverage(decay=0.9)

    def train_op():
        ema_op = ema.apply([mu, var])
        with tf.control_dependencies([ema_op]):
            return (tf.identity(mu), tf.identity(var))

    def test_op():
        moving_mu = ema.average(mu)
        moving_var = ema.average(var)
        return (moving_mu, moving_var)

    (mean, variance) = tf.cond(is_train, train_op, test_op)

    top = tf.nn.batch_normalization(bottom, mean, variance, shift, scale, 1e-4)

    return top


def conv2d(name, bottom, shape, strides, top_shape=None, with_bn=True, is_train=None):
    """
        Creates a convolution + BN block.
    """

    with tf.variable_scope(name) as scope:
        
        # apply batch normalization, if necessary
        bn = _bn(bottom, is_train) if with_bn else bottom

        # add convolution op
        weights = tf.get_variable("weights", shape=shape,
                                  initializer=tf.truncated_normal_initializer(stddev=0.02))
        if top_shape is not None:
            conv = tf.nn.conv2d_transpose(bn, weights, top_shape, strides, padding="SAME")
        else:
            conv = tf.nn.conv2d(bn, weights, strides, padding="SAME")

        # add biases
        bias_shape = [shape[-1]] if top_shape is None else [shape[-2]]
        biases = tf.get_variable("biases", shape=bias_shape,
                                 initializer=tf.constant_initializer())
        top = tf.nn.bias_add(conv, biases)

    return top



def linear(name, bottom, shape, with_bn=True, is_train=None):
    """
        Creates a fully connected + BN block.
    """

    with tf.variable_scope(name) as scope:

        # apply batch normalization, if necessary
        bn = _bn(bottom, is_train) if with_bn else bottom

        # inner product
        weights = tf.get_variable("weights", shape=shape,
                                  initializer=tf.truncated_normal_initializer(stddev=0.02))
        linear = tf.matmul(bn, weights)

        # add biases
        bias_shape = [shape[-1]]
        biases = tf.get_variable("biases", shape=bias_shape,
                                 initializer=tf.constant_initializer())
        top = tf.nn.bias_add(linear, biases)

    return top


def generator(data, is_train, side_length):
    """
        Builds the generator model.

        :param tensorflow.Tensor data:
            A 4-D input tensor with the last dimension Gaussian sampled.

        :param tensorflow.Tensor is_train:
            Determines whether or not the generator is used only for inference.

        :param int side_length:
            Image side length.
    """

    assert side_length % 16 == 0, "image side length must be divisible by 16"

    dim = side_length / 16
    (batch_size, z_len) = data.get_shape().as_list()

    # project block, 1024 outputs
    proj = tf.nn.relu(linear("g_proj", data, [z_len, dim * dim * 1024], with_bn=False))
    rshp = tf.reshape(proj, [batch_size, dim, dim, 1024])

    # conv1 block, 512 outputs
    dim *= 2
    conv1 = tf.nn.relu(conv2d("g_conv1", rshp, [5, 5, 512, 1024], STRIDE_2,
                              top_shape=[batch_size, dim, dim, 512], is_train=is_train))

    # conv2 block, 256 outputs
    dim *= 2
    conv2 = tf.nn.relu(conv2d("g_conv2", conv1, [5, 5, 256, 512], STRIDE_2,
                              top_shape=[batch_size, dim, dim, 256], is_train=is_train))

    # conv3 block, 128 outputs
    dim *= 2
    conv3 = tf.nn.relu(conv2d("g_conv3", conv2, [5, 5, 128, 256], STRIDE_2,
                              top_shape=[batch_size, dim, dim, 128], is_train=is_train))

    # conv4 block, 64 outputs
    dim *= 2
    conv4 = tf.nn.relu(conv2d("g_conv4", conv3, [5, 5, 64, 128], STRIDE_2,
                              top_shape=[batch_size, dim, dim, 64], is_train=is_train))

    # conv5 block, 3 outputs
    conv5 = tf.nn.tanh(conv2d("g_conv5", conv4, [3, 3, 3, 64], STRIDE_1,
                              top_shape=[batch_size, dim, dim, 3], is_train=is_train))

    top = conv5

    return top


def discriminator(data, is_train):
    """
        Builds the discriminator network.

        :param tensorflow.Tensor data:
            A 4-D tensor representing an input image.

        :param tensorflow.Tensor is_train:
            Determines whether or not the discriminator is used only for inference.
    """

    # conv1 block, 128 outputs
    conv1 = tf.nn.relu(conv2d("d_conv1", data, [5, 5, 3, 128], STRIDE_2, with_bn=False))

    # conv2 block, 256 outputs
    conv2 = tf.nn.relu(conv2d("d_conv2", conv1, [5, 5, 128, 256], STRIDE_2, is_train=is_train))

    # conv3 block, 512 outputs
    conv3 = tf.nn.relu(conv2d("d_conv3", conv2, [5, 5, 256, 512], STRIDE_2, is_train=is_train))

    # conv4 block, 1024 outputs
    conv4 = tf.nn.relu(conv2d("d_conv4", conv3, [5, 5, 512, 1024], STRIDE_2, is_train=is_train))

    # average pooling
    avg_pool = tf.reduce_mean(conv4, [1, 2])

    # fully connected
    classifier = linear("d_classifier", avg_pool, [1024, 1], with_bn=False)

    top = classifier

    return top

