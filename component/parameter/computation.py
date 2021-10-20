import numpy as np
from math import sqrt

# to use a single parameter for all filters
int_16_min = np.iinfo(np.int16).min


def z_coefficient(n):
    z = (3 * sqrt(n * (n - 1))) / (sqrt(2 * (2 * n + 5)))
    return z
