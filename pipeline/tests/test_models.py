import numpy as np
import pandas as pd
import pytest

from nbagm.models import (LAMBDA_GRID, fit_poisson, fit_ridge_imputer, fit_shot_model,
                          fit_stint_ridge, group_folds, logistic_slope, ols_residuals,
                          rule_a_weights)


def test_grid_matches_doc():
    assert len(LAMBDA_GRID) == 21 and LAMBDA_GRID[0] == 10 and LAMBDA_GRID[-1] == pytest.approx(1e5)


def test_group_folds_keep_games_together():
    f = group_folds(["a", "a", "b", "c", "d", "e", "f", "b"])
    assert f[0] == f[1] and f[2] == f[7] and set(f) == set(range(5))


def test_shot_model_learns_distance():
    rng = np.random.default_rng(0)
    n = 4000
    d = rng.uniform(0, 25, n)
    p = 1 / (1 + np.exp(-(1.0 - 0.1 * d)))
    shots = pd.DataFrame({"GAME_ID": rng.integers(0, 50, n), "SHOT_DISTANCE": d,
                          "LOC_X": rng.normal(0, 100, n), "ACTION_TYPE": "Jump Shot",
                          "SHOT_ZONE_AREA": "Center(C)", "SHOT_MADE_FLAG": rng.random(n) < p})
    m = fit_shot_model(shots)
    assert m.lam in m.cv_log_loss
    ph = m.predict(shots)
    assert np.corrcoef(ph, p)[0, 1] > 0.95


def test_stint_ridge_recovers_effects():
    rng = np.random.default_rng(1)
    players = list(range(40))
    off = {p: rng.normal(0, 3) for p in players}
    de = {p: rng.normal(0, 3) for p in players}
    rows = []
    for i in range(6000):
        ps = rng.choice(players, 10, replace=False)
        o, d = tuple(ps[:5]), tuple(ps[5:])
        w = rng.integers(5, 30)
        y = 110 + sum(off[p] for p in o) + sum(de[p] for p in d) + rng.normal(0, 60 / np.sqrt(w))
        rows.append((i % 300, o, d, y, w))
    r = fit_stint_ridge(pd.DataFrame(rows, columns=["game_id", "offense", "defense", "y", "w"]))
    assert np.corrcoef(r.offense[players], [off[p] for p in players])[0, 1] > 0.9
    assert np.corrcoef(r.defense[players], [de[p] for p in players])[0, 1] > 0.9


def test_poisson_regression():
    rng = np.random.default_rng(2)
    e = rng.uniform(100, 2000, 3000)
    x = rng.normal(0, 1, 3000)
    y = rng.poisson(e * np.exp(-4 + 0.5 * x))
    fit = fit_poisson(y, e, [x], ["x"])
    assert fit.coef == pytest.approx([-4, 0.5], abs=0.03)
    assert fit.expected(e[:1], [x[:1]])[0] == pytest.approx(e[0] * np.exp(fit.coef[0] + fit.coef[1] * x[0]))


def test_logistic_slope_and_non_existence():
    rng = np.random.default_rng(3)
    x = rng.uniform(0, 12, 5000)
    off = rng.normal(0, 0.5, 5000)
    y = rng.random(5000) < 1 / (1 + np.exp(-(off - 0.03 * x)))
    b, se = logistic_slope(y, x, off)
    assert abs(b + 0.03) < 3 * se
    assert np.isnan(logistic_slope([1, 1, 1], [1, 2, 3], [0, 0, 0])[0])
    assert np.isnan(logistic_slope([0, 0, 1, 1], [1, 2, 3, 4], [0, 0, 0, 0])[0])   # separation


def test_rule_a_drops_useless_components():
    rng = np.random.default_rng(4)
    Z = rng.normal(size=(500, 3))
    t = 2 * Z[:, 0] + Z[:, 1] - 0.5 * Z[:, 2] + rng.normal(0, 0.1, 500)
    w = rule_a_weights(Z, t)
    assert w.sum() == pytest.approx(1) and w[2] == 0 and w[0] > w[1] > 0


def test_ols_residuals_and_ridge_imputer():
    rng = np.random.default_rng(5)
    X = rng.normal(size=(200, 2))
    y = 3 + X @ [1.0, -2.0] + rng.normal(0, 0.1, 200)
    r = ols_residuals(y, X)
    assert abs(r.mean()) < 1e-9 and r.std() < 0.2
    imp = fit_ridge_imputer(X, y)
    assert np.corrcoef(imp.predict(X), y)[0, 1] > 0.99
