import numpy as np
import pytest

from nbagm.shrinkage import (ShrinkageError, fit_beta_binomial, fit_gamma_poisson,
                             fit_scaled_inv_chi2)


def test_beta_binomial_recovers_known_prior():
    rng = np.random.default_rng(0)
    true = rng.beta(30, 70, size=4000)            # mean 0.3, alpha+beta = 100
    n = rng.integers(50, 600, size=4000)
    s = rng.binomial(n, true)
    prior = fit_beta_binomial(s, n)
    assert prior.mean == pytest.approx(0.3, abs=0.005)
    assert prior.alpha + prior.beta == pytest.approx(100, rel=0.15)


def test_beta_binomial_shrinks_small_samples_harder():
    rng = np.random.default_rng(1)
    n = rng.integers(100, 500, size=500)
    s = rng.binomial(n, rng.beta(20, 30, size=500))
    prior = fit_beta_binomial(s, n)
    small, large = prior.posterior_mean([5, 500], [5, 500])   # both 100% observed
    assert small < large < 1.0
    assert abs(small - prior.mean) < abs(large - prior.mean)


def test_zero_opportunity_player_gets_prior_mean_and_is_excluded_from_fit():
    s = np.array([10, 20, 30, 0])
    n = np.array([100, 100, 100, 0])
    prior = fit_beta_binomial(s, n)
    assert prior.n_players == 3
    assert prior.posterior_mean(0, 0) == pytest.approx(prior.mean)


def test_no_between_player_variance_gives_point_mass_at_mean():
    prior = fit_beta_binomial([50, 50, 50], [100, 100, 100])
    assert np.isinf(prior.alpha)
    assert prior.posterior_mean([0], [10])[0] == pytest.approx(0.5)


def test_beta_binomial_rejects_non_proportions():
    with pytest.raises(ShrinkageError):
        fit_beta_binomial([12, 3], [10, 10])


def test_gamma_poisson_formula_matches_doc():
    rng = np.random.default_rng(2)
    rates = rng.gamma(shape=25, scale=1.0 / 25, size=3000)   # mean 1.0, k = 25
    e = rng.integers(20, 300, size=3000)
    x = rng.poisson(rates * e)
    prior = fit_gamma_poisson(x, e)
    assert prior.theta == pytest.approx(1.0, abs=0.02)
    assert prior.k == pytest.approx(25, rel=0.25)
    # doc 02: shrunk = (points + k) / (possessions + k/theta)
    assert prior.posterior_mean(30, 20) == pytest.approx((30 + prior.k) / (20 + prior.k / prior.theta))


def test_scaled_inv_chi2_recovers_prior_mean():
    rng = np.random.default_rng(3)
    nu0, tau2 = 20.0, 4.0
    sigma2 = nu0 * tau2 / rng.chisquare(nu0, size=5000)
    dof = rng.integers(10, 80, size=5000)
    s2 = sigma2 * rng.chisquare(dof) / dof
    prior = fit_scaled_inv_chi2(s2, dof)
    assert prior.mean == pytest.approx(nu0 * tau2 / (nu0 - 2), rel=0.05)
    assert prior.nu0 == pytest.approx(nu0, rel=0.3)
