import copy
import logging
from typing import Callable, List, Union

import numpy as np
import tensorflow as tf
import typing
from tensorflow.python.util import tf_inspect

NoneType = type(None)


def create_logger(name=None):
    return logging.getLogger('Temporary Logger Solution')


def default_jitter_eye(num_rows: int, num_columns: int = None, value: float = None) -> float:
    value = default_jitter() if value is None else value
    num_rows = int(num_rows)
    num_columns = int(num_columns) if num_columns is not None else num_columns
    return tf.eye(num_rows, num_columns=num_columns, dtype=default_float()) * value


def default_jitter() -> float:
    return 1e-6


def default_float() -> float:
    return np.float64


def default_int() -> int:
    return np.int32


def leading_transpose(tensor: tf.Tensor, perm: List[Union[int, type(...)]],
                      leading_dim: int = 0) -> tf.Tensor:
    """
    Transposes tensors with leading dimensions. Leading dimensions in
    permutation list represented via ellipsis `...`.
    When leading dimensions are found, `transpose` method
    considers them as a single grouped element indexed by 0 in `perm` list. So, passing
    `perm=[-2, ..., -1]`, you assume that your input tensor has [..., A, B] shape,
    and you want to move leading dims between A and B dimensions.
    Dimension indices in permutation list can be negative or positive. Valid positive
    indices start from 1 up to the tensor rank, viewing leading dimensions `...` as zero
    index.
    Example:
        a = tf.random.normal((1, 2, 3, 4, 5, 6))  # [..., A, B, C],
                                                  # where A is 1st element,
                                                  # B is 2nd element and
                                                  # C is 3rd element in
                                                  # permutation list,
                                                  # leading dimentions are [1, 2, 3]
                                                  # which are 0th element in permutation
                                                  # list
        b = leading_transpose(a, [3, -3, ..., -2])  # [C, A, ..., B]
        sess.run(b).shape
        output> (6, 4, 1, 2, 3, 5)
    :param tensor: TensorFlow tensor.
    :param perm: List of permutation indices.
    :returns: TensorFlow tensor.
    :raises: ValueError when `...` cannot be found.
    """
    perm = copy.copy(perm)
    idx = perm.index(...)
    perm[idx] = leading_dim

    rank = tf.rank(tensor)
    perm_tf = perm % rank

    leading_dims = tf.range(rank - len(perm) + 1)
    perm = tf.concat([perm_tf[:idx], leading_dims, perm_tf[idx + 1:]], 0)
    return tf.transpose(tensor, perm)


def set_trainable(model: tf.Module, flag: bool = False):
    for variable in model.trainable_variables:
        variable._trainable = flag


def training_loop(closure: Callable[..., tf.Tensor],
                  optimizer=tf.optimizers.Adam(),
                  var_list: List[tf.Variable] = None,
                  jit=True,
                  maxiter=1e3):
    """
    Simple generic training loop. At each iteration uses a GradientTape to compute
    the gradients of a loss function with respect to a set of variables.

    :param closure: Callable that constructs a loss function based on data and model being trained
    :param optimizer: tf.optimizers or tf.keras.optimizers that updates variables by applying the
    corresponding loss gradients
    :param var_list: List of model variables to be learnt during training
    :param maxiter: Maximum number of
    :return:
    """
    def optimization_step():
        with tf.GradientTape() as tape:
            tape.watch(var_list)
            loss = closure()
            grads = tape.gradient(loss, var_list)
        optimizer.apply_gradients(zip(grads, var_list))

    if jit:
        optimization_step = tf.function(optimization_step)

    for _ in range(int(maxiter)):
        optimization_step()


def broadcasting_elementwise(op, a, b):
    """
    Apply binary operation `op` to every pair in tensors `a` and `b`.

    :param op: binary operator on tensors, e.g. tf.add, tf.substract
    :param a: tf.Tensor, shape [n_1, ..., n_a]
    :param b: tf.Tensor, shape [m_1, ..., m_b]
    :return: tf.Tensor, shape [n_1, ..., n_a, m_1, ..., m_b]
    """
    flatres = op(tf.reshape(a, [-1, 1]), tf.reshape(b, [1, -1]))
    return tf.reshape(flatres, tf.concat([tf.shape(a), tf.shape(b)], 0))


class Dispatcher:
    def __init__(self, name: str):
        self.name = name
        self.REF_DICT = {}

    def __repr__(self):
        return self.name

    def registered_fn(self, type_a, type_b):
        """Gets the function registered for classes a and b."""
        hierarchy_a = tf_inspect.getmro(type_a)
        hierarchy_b = tf_inspect.getmro(type_b)
        dist_to_children = None
        fn = None
        for mro_to_a, parent_a in enumerate(hierarchy_a):
            for mro_to_b, parent_b in enumerate(hierarchy_b):
                candidate_dist = mro_to_a + mro_to_b
                candidate_fn = self.REF_DICT.get((parent_a, parent_b), None)
                if not fn or (candidate_fn and candidate_dist < dist_to_children):
                    dist_to_children = candidate_dist
                    fn = candidate_fn
        return fn

    def register(self, type_A, type_B):
        register_object = Register(self, type_A, type_B)
        def _(func):
            register_object(func)
            return func
        return _


class Register:
    def __init__(self, dispatch: Dispatcher, type_A, type_B):
        self._key = (type_A, type_B)
        self._ref_dict = dispatch.REF_DICT
        self.name = dispatch.name


    def __call__(self, fn):
        """Perform the Multioutput Conditional registration.

        Args:
          fn: The function to use for the KL divergence.

        Returns:
          fn

        Raises:
          TypeError: if fn is not a callable.
          ValueError: if a function has already been registered for the given argument classes.
        """
        if not callable(fn):
            raise TypeError("fn must be callable, received: %s" % fn)
        if self._key in self._ref_dict:
            raise ValueError("%s(%s, %s) has already been registered to: %s"
                             % (self.name, self._key[0].__name__, self._key[1].__name__,
                                self._ref_dict[self._key]))
        self._ref_dict[self._key] = fn
        return fn

if __name__ == '__main__':
    conditional_dispatcher = Dispatcher('conditional')

    @conditional_dispatcher.register(int, str)
    def foo(a, b):
        print(a, b)

    @conditional_dispatcher.register(str, int)
    def foo2(b, a):
        pass

    def foot(a, b):
        foo_fn = conditional_dispatcher.registered_fn(type(a), type(b))
        return foo_fn(a, b)
    print(conditional_dispatcher.REF_DICT)
    foo(1,'s')
