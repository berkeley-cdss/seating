def arr_to_dict(arr, key_getter=lambda x: x):
    """
    Convert an array to a dictionary, grouping by the key returned by key_getter.
    """
    from collections import defaultdict
    dic = defaultdict(list)
    for x in arr:
        dic[key_getter(x)].append(x)
    return dic


def str_set_to_set(s, force_lower=True, ignore_empty=True):
    import re
    if force_lower:
        s = s.lower()
    rlt = set(re.split(r',', s)) if s else set()
    if ignore_empty:
        rlt.discard('')
    return rlt


def set_to_str(s):
    return ','.join(s)
