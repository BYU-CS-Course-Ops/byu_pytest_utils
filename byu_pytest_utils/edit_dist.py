from typing import Optional

def edit_dist(
    observed: str,
    expected: str,
    GAP='~',
    MATCH=1,
    SUB=-1,
    GAP_OPEN=-3,
    GAP_EXTEND=-1
) -> tuple[int, str, str]:
    """
    Align seq1 against seq2 using Needleman-Wunsch
    Put seq1 on left (j) and seq2 on top (i)
    => matrix[i][j]
    """

    len1, len2 = len(observed), len(expected)
    score = [[0] * (len1 + 1) for _ in range(len2 + 1)]
    path: list[list[Optional[tuple[int, int]]]] = [[None] * (len1 + 1) for _ in range(len2 + 1)]

    # initialize first row/column
    score[1][0] = GAP_OPEN + GAP_EXTEND
    path[1][0] = (0, 0)
    for i in range(2, len2 + 1):
        score[i][0] = score[i - 1][0] + GAP_EXTEND
        path[i][0] = (i - 1, 0)

    score[0][1] = GAP_OPEN + GAP_EXTEND
    path[0][1] = (0, 0)
    for j in range(2, len1 + 1):
        score[0][j] = score[0][j - 1] + GAP_EXTEND
        path[0][j] = (0, j - 1)

    # fill matrix
    for i in range(1, len2 + 1):
        for j in range(1, len1 + 1):
            match = score[i - 1][j - 1] + (MATCH if observed[j - 1] == expected[i - 1] else SUB)
            gap_i = score[i - 1][j] + GAP_EXTEND + (GAP_OPEN if path[i - 1][j] != (i - 2, j) else 0)
            gap_j = score[i][j - 1] + GAP_EXTEND + (GAP_OPEN if path[i][j - 1] != (i, j - 2) else 0)

            if gap_i >= match and gap_i >= gap_j:
                score[i][j] = gap_i
                path[i][j] = (i - 1, j)
            elif gap_j >= match:
                score[i][j] = gap_j
                path[i][j] = (i, j - 1)
            else:
                score[i][j] = match
                path[i][j] = (i - 1, j - 1)

    # traceback
    i, j = len2, len1
    align1, align2 = [], []
    while (i, j) != (0, 0):
        pi, pj = path[i][j] #type: ignore
        if pi == i - 1 and pj == j - 1:
            align1.append(observed[j - 1])
            align2.append(expected[i - 1])
        elif pi == i - 1:
            align1.append(GAP)
            align2.append(expected[i - 1])
        else:
            align1.append(observed[j - 1])
            align2.append(GAP)
        i, j = pi, pj

    return score[len2][len1], ''.join(reversed(align1)), ''.join(reversed(align2))
