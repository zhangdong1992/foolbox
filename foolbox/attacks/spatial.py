# -*- coding: utf-8 -*-
from __future__ import division

import numpy as np
from itertools import product
from scipy.ndimage import rotate, shift
import operator
from tqdm import tqdm

from foolbox.attacks.base import Attack
from foolbox.attacks.base import call_decorator


class SpatialAttack(Attack):
    """Adversarially chosen rotations and translations [1]. This implementation
    is based on the reference implementation by Madry et al.
    https://github.com/MadryLab/adversarial_spatial

    References
    ----------
    .. [1] Logan Engstrom*, Brandon Tran*, Dimitris Tsipras*,
           Ludwig Schmidt, Aleksander Mądry: "A Rotation and a
           Translation Suffice: Fooling CNNs with Simple Transformations",
           http://arxiv.org/abs/1712.02779
    """

    @call_decorator
    def __call__(self, input_or_adv, label=None, unpack=True,
                 do_rotations=True, do_translations=True,
                 x_shift_limits=[-5, 5], y_shift_limits=[-5, 5],
                 angular_limits=[-5, 5], granularity=10,
                 random_sampling=False, abort_early=True):

        """Adversarially chosen rotations and translations.

        Parameters
        ----------
        input_or_adv : `numpy.ndarray` or :class:`Adversarial`
            The original, unperturbed input as a `numpy.ndarray` or
            an :class:`Adversarial` instance.
        label : int
            The reference label of the original input. Must be passed
            if `a` is a `numpy.ndarray`, must not be passed if `a` is
            an :class:`Adversarial` instance.
        unpack : bool
            If true, returns the adversarial input, otherwise returns
            the Adversarial object.
        do_rotations : bool
            If False no rotations will be applied to the image.
        do_translations : bool
            If False no translations will be applied to the image.
        x_shift_limits : int or [int, int]
            Limits for horizontal translations in pixels. If one integer is
            provided the limits will be [-dx_limits, dx_limits].
        y_shift_limits : int or [int, int]
            Limits for vertical translations in pixels. If one integer is
            provided the limits will be [-dy_limits, dy_limits].
        angular_limits : int or [int, int]
            Limits for rotations in degrees. If one integer is
            provided the limits will be [-drot_limits, drot_limits].
        granularity : int
            Density of sampling within limits for each dimension.
        random_sampling : bool
            If True we sample translations/rotations randomly within limits,
            otherwise we use a regular grid.
        abort_early : bool
            If True, the attack stops as soon as it finds an adversarial.
        """

        a = input_or_adv
        del input_or_adv
        del label
        del unpack

        min_, max_ = a.bounds()

        def get_samples(limits, num, do_flag):
            # get regularly spaced or random samples within limits
            lb, up = [-limits, limits] if type(limits) == int else limits

            if not do_flag:
                return [0]
            elif random_sampling:
                return np.random.uniform(lb, up, num)
            else:
                return np.linspace(lb, up, num)

        def crop_center(img):
            # crop center of the image (of the size of the original image)
            start = tuple(map(lambda a, da: a // 2 - da // 2, img.shape,
                              a.original_image.shape))
            end = tuple(map(operator.add, start, a.original_image.shape))
            slices = tuple(map(slice, start, end))
            return img[slices]

        x_shifts = get_samples(x_shift_limits, granularity, do_translations)
        y_shifts = get_samples(y_shift_limits, granularity, do_translations)
        rotations = get_samples(angular_limits, granularity, do_rotations)

        transformations = product(x_shifts, y_shifts, rotations)

        for x_shift, y_shift, angle in transformations:
            # translate & rotate image
            axes = [0, 1] if a.channel_axis(batch=False) == 2 else [1, 2]
            channel_axis = a.channel_axis(batch=False)
            xy_shift = [0, x_shift, y_shift] if channel_axis == 0 \
                                             else [x_shift, y_shift, 0]

            # rotate image (increases size)
            x = a.original_image
            x = rotate(x, angle=angle, axes=axes, reshape=True, order=1)

            # translate image
            x = shift(x, shift=xy_shift, mode='constant')

            # crop center
            x = crop_center(x)

            # ensure values are in range
            x = np.clip(x, min_ + 1e-8, max_ - 1e-8)

            # test image
            _, is_adv = a.predictions(x)

            if abort_early and is_adv:
                break