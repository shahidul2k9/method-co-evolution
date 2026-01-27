import numpy as np

def ecdf_with_rank(series):
    s = series.sort_values()
    y = s.rank(method="max", pct=True)
    return s, y


def ecdf(a):
    x, counts = np.unique(a, return_counts=True)
    cusum = np.cumsum(counts)
    return x, cusum / cusum[-1]


GRAPH_STYLES = ["-", "--", "-.", ":", "--", "--", "-.", ":"]
GRAPH_MARKS = ["^", "d", "o", "v", "p", "s", "<", ">"]
GRAPH_WIDTHS = [4, 4, 4, 4, 3, 3, 3, 3]
GRAPH_MARKER_SIZES = [10, 10, 12, 14, 20, 10, 12, 15]
GRAPH_MARKER_COLORS = ['r', 'b', 'brown', '#c994c7', '#0F52BA', '#ff7518', '#6CA939', '#636363']
GRAPH_GAPS = [3, 3, 6, 5, 5, 4, 4, 4]