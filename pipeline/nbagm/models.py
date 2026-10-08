"""Regression machinery used by doc 02: the E1 shot-make models, the stint ridge
(RAPM family), Poisson expectation models (E3), Rule A's non-negative least
squares, OLS residuals and the ridge imputation of missing combine tests.

Every model here is fit on real league data passed in by the caller; nothing
about a particular player is encoded. Penalties are chosen by cross-validation
over doc 02's grid: 21 log-spaced values from 10^1 to 10^5.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import nnls

LAMBDA_GRID = np.logspace(1, 5, 21)
N_FOLDS = 5


class ModelError(ValueError):
    pass


def group_folds(groups, k=N_FOLDS):
    """Fold index per row; every row of one group (game) lands in the same fold.
    Groups are assigned round-robin in sorted order, so folds are deterministic."""
    groups = pd.Series(np.asarray(groups)).astype(str)
    uniq = np.sort(groups.unique())
    if len(uniq) < k:
        raise ModelError(f"cross-validation needs at least {k} groups, got {len(uniq)}")
    fold_of = {g: i % k for i, g in enumerate(uniq)}
    return groups.map(fold_of).to_numpy()


# --------------------------------------------------------------------------- #
# E1: ridge logistic shot-make models
# --------------------------------------------------------------------------- #

@dataclass
class ShotModel:
    lam: float
    cv_log_loss: dict
    n_shots: int
    _enc: object
    _mean: np.ndarray
    _sd: np.ndarray
    _clf: object
    _cats: tuple

    def predict(self, shots):
        return self._clf.predict_proba(_shot_design(shots, self._enc, self._mean, self._sd,
                                                    self._cats)[0])[:, 1]


def _shot_continuous(shots):
    d = shots["SHOT_DISTANCE"].to_numpy(dtype=float)
    return np.column_stack([d, d * d, np.abs(shots["LOC_X"].to_numpy(dtype=float))])


def _shot_design(shots, enc, mean, sd, cats):
    from sklearn.preprocessing import OneHotEncoder
    cont = _shot_continuous(shots)
    if enc is None:
        enc = OneHotEncoder(handle_unknown="ignore", sparse_output=True)
        enc.fit(shots[list(cats)].astype(str))
        mean, sd = cont.mean(axis=0), cont.std(axis=0)
        sd = np.where(sd > 0, sd, 1.0)
    X = sparse.hstack([enc.transform(shots[list(cats)].astype(str)),
                       sparse.csr_matrix((cont - mean) / sd)]).tocsr()
    return X, enc, mean, sd


def fit_shot_model(shots, include_shot_type=False, name="E1"):
    """make ~ one-hot(ACTION_TYPE) + SHOT_DISTANCE + SHOT_DISTANCE^2 + |LOC_X| +
    one-hot(SHOT_ZONE_AREA) [+ one-hot(SHOT_TYPE) for E1-all]; L2 penalty lambda
    (sklearn C = 1/lambda), unpenalized intercept, lambda by 5-fold CV split by game
    minimizing held-out log-loss."""
    from sklearn.linear_model import LogisticRegression
    if len(shots) == 0:
        raise ModelError(f"{name}: no shots")
    y = shots["SHOT_MADE_FLAG"].to_numpy(dtype=int)
    if y.min() == y.max():
        raise ModelError(f"{name}: every shot has the same result")
    cats = ("ACTION_TYPE", "SHOT_ZONE_AREA") + (("SHOT_TYPE",) if include_shot_type else ())
    folds = group_folds(shots["GAME_ID"])
    losses = {}
    for lam in LAMBDA_GRID:
        total, n = 0.0, 0
        for f in range(N_FOLDS):
            tr, te = folds != f, folds == f
            if y[tr].min() == y[tr].max():
                raise ModelError(f"{name}: a training fold has one class only")
            Xtr, enc, m, s = _shot_design(shots[tr], None, None, None, cats)
            Xte = _shot_design(shots[te], enc, m, s, cats)[0]
            clf = LogisticRegression(C=1.0 / lam, max_iter=2000).fit(Xtr, y[tr])
            p = np.clip(clf.predict_proba(Xte)[:, 1], 1e-12, 1 - 1e-12)
            total += -np.sum(y[te] * np.log(p) + (1 - y[te]) * np.log(1 - p))
            n += te.sum()
        losses[float(lam)] = total / n
    lam = min(losses, key=losses.get)
    X, enc, m, s = _shot_design(shots, None, None, None, cats)
    clf = LogisticRegression(C=1.0 / lam, max_iter=2000).fit(X, y)
    return ShotModel(lam, losses, len(shots), enc, m, s, clf, cats)


# --------------------------------------------------------------------------- #
# Stint ridge regressions (RAPM family)
# --------------------------------------------------------------------------- #

@dataclass
class StintRidge:
    lam: float
    intercept: float
    offense: pd.Series       # player_id -> offense coefficient
    defense: pd.Series       # player_id -> defense coefficient (effect on opponent y)
    cv_mse: dict
    n_rows: int


def _ridge_solve(A, b, lam):
    """Solve (A + lam*P) x = b where P penalizes all but the first (intercept) column."""
    P = np.ones(len(b))
    P[0] = 0.0
    return np.linalg.solve(A + lam * np.diag(P), b)


def fit_stint_ridge(rows, name="ridge"):
    """rows: DataFrame with columns game_id, offense (tuple of 5 ids), defense (tuple of 5
    ids), y, w. Two coefficients per player plus an unpenalized intercept; weighted least
    squares with ridge penalty lambda * ||beta||^2; lambda by 5-fold CV (folds by game)
    minimizing held-out weighted squared error."""
    rows = rows[rows["w"] > 0].reset_index(drop=True)
    if len(rows) == 0:
        raise ModelError(f"{name}: no stints with possessions")
    players = sorted({p for col in ("offense", "defense") for t in rows[col] for p in t})
    idx = {p: i for i, p in enumerate(players)}
    n_p = len(players)
    r, c = [], []
    for i, (off, de) in enumerate(zip(rows["offense"], rows["defense"])):
        for p in off:
            r.append(i)
            c.append(1 + idx[p])
        for p in de:
            r.append(i)
            c.append(1 + n_p + idx[p])
    r += list(range(len(rows)))
    c += [0] * len(rows)
    X = sparse.csr_matrix((np.ones(len(r)), (r, c)), shape=(len(rows), 1 + 2 * n_p))
    y, w = rows["y"].to_numpy(float), rows["w"].to_numpy(float)
    folds = group_folds(rows["game_id"])

    def normal(mask):
        Xm = X[mask]
        Wm = sparse.diags(w[mask])
        return (Xm.T @ Wm @ Xm).toarray(), Xm.T @ (w[mask] * y[mask])

    A_tot, b_tot = normal(np.ones(len(rows), bool))
    parts = [normal(folds == f) for f in range(N_FOLDS)]
    mse = {}
    for lam in LAMBDA_GRID:
        err, wsum = 0.0, 0.0
        for f, (A_f, b_f) in enumerate(parts):
            beta = _ridge_solve(A_tot - A_f, b_tot - b_f, lam)
            te = folds == f
            resid = y[te] - X[te] @ beta
            err += np.sum(w[te] * resid ** 2)
            wsum += w[te].sum()
        mse[float(lam)] = err / wsum
    lam = min(mse, key=mse.get)
    beta = _ridge_solve(A_tot, b_tot, lam)
    return StintRidge(lam, float(beta[0]),
                      pd.Series(beta[1:1 + n_p], index=players),
                      pd.Series(beta[1 + n_p:], index=players), mse, len(rows))


# --------------------------------------------------------------------------- #
# E3: Poisson regression with exposure offset (maximum likelihood)
# --------------------------------------------------------------------------- #

@dataclass
class PoissonFit:
    coef: np.ndarray        # intercept first
    names: tuple
    n: int

    def expected(self, exposure, X):
        X = np.column_stack([np.ones(len(exposure))] + [np.asarray(x, float) for x in X])
        return np.asarray(exposure, float) * np.exp(X @ self.coef)


def fit_poisson(counts, exposure, covariates, names, name="E3"):
    """counts ~ Poisson(exposure * exp(a + b.x)), fit by Newton-Raphson on every player
    with positive exposure."""
    y = np.asarray(counts, float)
    e = np.asarray(exposure, float)
    Xc = [np.asarray(x, float) for x in covariates]
    ok = (e > 0) & np.all([np.isfinite(x) for x in Xc], axis=0) if Xc else (e > 0)
    if ok.sum() <= len(Xc) + 1:
        raise ModelError(f"{name}: too few players with exposure")
    X = np.column_stack([np.ones(ok.sum())] + [x[ok] for x in Xc])
    off = np.log(e[ok])
    yy = y[ok]
    beta = np.zeros(X.shape[1])
    beta[0] = np.log(max(yy.sum(), 1e-12) / e[ok].sum())
    for _ in range(100):
        mu = np.exp(X @ beta + off)
        grad = X.T @ (yy - mu)
        H = X.T @ (mu[:, None] * X)
        step = np.linalg.solve(H, grad)
        beta += step
        if np.max(np.abs(step)) < 1e-10:
            break
    else:
        raise ModelError(f"{name}: Poisson regression did not converge")
    return PoissonFit(beta, tuple(names), int(ok.sum()))


# --------------------------------------------------------------------------- #
# Per-player logistic slope with an offset (Stamina)
# --------------------------------------------------------------------------- #

def logistic_slope(y, x, offset, max_iter=100):
    """MLE of b in logit P(y) = offset + a + b*x. Returns (b, se) or (nan, nan) when the
    MLE does not exist (one outcome only, no spread in x, or separation)."""
    y, x, offset = (np.asarray(v, float) for v in (y, x, offset))
    if len(y) < 3 or y.min() == y.max() or np.ptp(x) == 0:
        return np.nan, np.nan
    X = np.column_stack([np.ones(len(y)), x])
    beta = np.zeros(2)
    for _ in range(max_iter):
        eta = np.clip(offset + X @ beta, -30, 30)
        p = 1 / (1 + np.exp(-eta))
        W = p * (1 - p)
        H = X.T @ (W[:, None] * X)
        if np.linalg.cond(H) > 1e12:
            return np.nan, np.nan
        step = np.linalg.solve(H, X.T @ (y - p))
        beta += step
        if not np.all(np.isfinite(beta)) or np.abs(beta[1]) * np.ptp(x) > 50:
            return np.nan, np.nan          # diverging: separation
        if np.max(np.abs(step)) < 1e-9:
            cov = np.linalg.inv(H)
            return float(beta[1]), float(np.sqrt(cov[1, 1]))
    return np.nan, np.nan


# --------------------------------------------------------------------------- #
# Rule A, OLS residuals, ridge imputation
# --------------------------------------------------------------------------- #

def rule_a_weights(Z, target):
    """Non-negative least squares of the target on the component Z-scores, with a free
    intercept (both sides centered); coefficients rescaled to sum to 1."""
    Z, t = np.asarray(Z, float), np.asarray(target, float)
    ok = np.all(np.isfinite(Z), axis=1) & np.isfinite(t)
    Zc = Z[ok] - Z[ok].mean(axis=0)
    w, _ = nnls(Zc, t[ok] - t[ok].mean())
    if w.sum() <= 0:
        raise ModelError("Rule A: every component got weight 0")
    return w / w.sum()


def ols_residuals(y, design):
    """Residuals of y on [1, design] by least squares (rank-deficient designs allowed)."""
    y = np.asarray(y, float)
    X = np.column_stack([np.ones(len(y))] + ([np.asarray(design, float)] if np.size(design) else []))
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ beta


def one_hot(labels):
    labels = pd.Series(labels).astype(str)
    return pd.get_dummies(labels, dtype=float).to_numpy()


@dataclass
class RidgeImputer:
    lam: float
    cv_mse: dict
    n_fit: int
    mean: np.ndarray
    sd: np.ndarray
    beta: np.ndarray

    def predict(self, X):
        X = (np.asarray(X, float) - self.mean) / self.sd
        return self.beta[0] + X @ self.beta[1:]


def _ridge_fit(X, y, lam):
    A = np.column_stack([np.ones(len(y)), X])
    P = np.eye(A.shape[1])
    P[0, 0] = 0.0
    return np.linalg.solve(A.T @ A + lam * P, A.T @ y)


def fit_ridge_imputer(X, y, name="ridge"):
    """Linear ridge on standardized features, unpenalized intercept, lambda by 5-fold CV
    over the doc 02 grid (rows in the given order, assigned round-robin to folds)."""
    X, y = np.asarray(X, float), np.asarray(y, float)
    if len(y) < 2 * N_FOLDS:
        raise ModelError(f"{name}: only {len(y)} players have this test")
    mean, sd = X.mean(axis=0), X.std(axis=0)
    sd = np.where(sd > 0, sd, 1.0)
    Xs = (X - mean) / sd
    folds = np.arange(len(y)) % N_FOLDS
    mse = {}
    for lam in LAMBDA_GRID:
        err = 0.0
        for f in range(N_FOLDS):
            tr, te = folds != f, folds == f
            m, s = X[tr].mean(axis=0), X[tr].std(axis=0)
            s = np.where(s > 0, s, 1.0)
            b = _ridge_fit((X[tr] - m) / s, y[tr], lam)
            err += np.sum((y[te] - b[0] - ((X[te] - m) / s) @ b[1:]) ** 2)
        mse[float(lam)] = err / len(y)
    lam = min(mse, key=mse.get)
    return RidgeImputer(lam, mse, len(y), mean, sd, _ridge_fit(Xs, y, lam))
