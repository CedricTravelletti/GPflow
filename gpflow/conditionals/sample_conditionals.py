import tensorflow as tf
import numpy as np
from multipledispatch import dispatch

from .conditionals import conditional
from .dispatch import sample_conditional_dispatcher
from .util import sample_mvn
from ..features import InducingFeature
from ..kernels import Kernel
from ..util import create_logger, Register

logger = create_logger()
dispatch


def sample_conditional(Xnew: tf.Tensor,
                       feature: InducingFeature, kernel: Kernel,
                       function: tf.Tensor, full_cov=False, full_output_cov=False, q_sqrt=None,
                       white=False, num_samples=None):
    sample_conditional_fn = sample_conditional_dispatcher.registered_fn(type(feature), type(kernel))
    return sample_conditional_fn(Xnew, feature, kernel, function, full_cov, full_output_cov,
                                 q_sqrt, white, num_samples)


@sample_conditional_dispatcher.register(np.ndarray, Kernel)
@sample_conditional_dispatcher.register(tf.Tensor, Kernel)
@sample_conditional_dispatcher.register(InducingFeature, Kernel)
def _sample_conditional(Xnew: tf.Tensor,
                        feature: InducingFeature,
                        kernel: Kernel,
                        function: tf.Tensor,
                        full_cov=False,
                        full_output_cov=False,
                        q_sqrt=None,
                        white=False,
                        num_samples=None):
    """
    `sample_conditional` will return a sample from the conditional distribution.
    In most cases this means calculating the conditional mean m and variance v and then
    returning m + sqrt(v) * eps, with eps ~ N(0, 1).
    However, for some combinations of Mok and Mof more efficient sampling routines exists.
    The dispatcher will make sure that we use the most efficient one.
    :return: samples, mean, cov
        samples has shape [num_samples, N, P] or [N, P] if num_samples is None
        mean and cov as for conditional()
    """

    if full_cov and full_output_cov:
        msg = "The combination of both `full_cov` and `full_output_cov` is not permitted."
        raise NotImplementedError(msg)

    mean, cov = conditional(Xnew, feature, kernel, function,
                            q_sqrt=q_sqrt, white=white,
                            full_cov=full_cov, full_output_cov=full_output_cov)
    if full_cov:
        # mean: [..., N, P]
        # cov: [..., P, N, N]
        mean_for_sample = tf.linalg.adjoint(mean)  # [..., P, N]
        samples = sample_mvn(mean_for_sample, cov, 'full',
                             num_samples=num_samples)  # [..., (S), P, N]
        samples = tf.linalg.adjoint(samples)  # [..., (S), P, N]
    else:
        # mean: [..., N, P]
        # cov: [..., N, P] or [..., N, P, P]
        cov_structure = "full" if full_output_cov else "diag"
        samples = sample_mvn(mean, cov, cov_structure, num_samples=num_samples)  # [..., (S), P, N]

    return samples, mean, cov
