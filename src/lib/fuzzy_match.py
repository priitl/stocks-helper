"""Fuzzy matching utilities using Levenshtein distance.

Used for ticker validation to suggest corrections for typos.
"""


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings.

    The Levenshtein distance is the minimum number of single-character edits
    (insertions, deletions, or substitutions) required to change one string
    into the other.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Integer distance (0 means identical strings)

    Example:
        >>> levenshtein_distance("APPL", "AAPL")
        1
        >>> levenshtein_distance("XYZZ", "AAPL")
        4
    """
    if s1 == s2:
        return 0

    len1, len2 = len(s1), len(s2)

    # Create a matrix to store distances
    # dp[i][j] = distance between s1[:i] and s2[:j]
    dp = [[0] * (len2 + 1) for _ in range(len1 + 1)]

    # Initialize base cases
    for i in range(len1 + 1):
        dp[i][0] = i  # Distance from s1[:i] to empty string
    for j in range(len2 + 1):
        dp[0][j] = j  # Distance from empty string to s2[:j]

    # Fill the matrix
    for i in range(1, len1 + 1):
        for j in range(1, len2 + 1):
            if s1[i - 1] == s2[j - 1]:
                # Characters match, no edit needed
                dp[i][j] = dp[i - 1][j - 1]
            else:
                # Take minimum of insert, delete, or substitute
                dp[i][j] = 1 + min(
                    dp[i - 1][j],  # Delete from s1
                    dp[i][j - 1],  # Insert into s1
                    dp[i - 1][j - 1],  # Substitute
                )

    return dp[len1][len2]


def fuzzy_match_ticker(
    ticker: str,
    known_tickers: set[str],
    threshold: int = 2,
    max_results: int = 3,
) -> list[str]:
    """Find similar tickers using fuzzy matching.

    Uses Levenshtein distance to find tickers within the threshold distance.
    Returns the closest matches sorted by distance.

    Args:
        ticker: Ticker to match (e.g., "APPL")
        known_tickers: Set of valid tickers
        threshold: Maximum Levenshtein distance (default: 2)
        max_results: Maximum number of suggestions (default: 3)

    Returns:
        List of similar tickers sorted by distance (closest first)

    Example:
        >>> known = {"AAPL", "APL", "GOOG", "MSFT"}
        >>> fuzzy_match_ticker("APPL", known, threshold=2)
        ["AAPL", "APL"]
    """
    if not ticker or not known_tickers:
        return []

    # Calculate distances for all known tickers
    distances: list[tuple[int, str]] = []
    for known_ticker in known_tickers:
        distance = levenshtein_distance(ticker.upper(), known_ticker.upper())
        if distance <= threshold:
            distances.append((distance, known_ticker))

    # Sort by distance (closest first) and return top results
    distances.sort(key=lambda x: (x[0], x[1]))  # Sort by distance, then alphabetically
    return [t for _, t in distances[:max_results]]
