from warnings import warn

import numpy as np
from scipy.optimize import minimize_scalar
from sklearn.base import BaseEstimator, OutlierMixin
from sklearn.mixture import BayesianGaussianMixture
from sklearn.utils.validation import check_is_fitted, check_array, FLOAT_DTYPES

from scipy.stats import gaussian_kde


class BayesianGMMOutlierDetector(OutlierMixin, BaseEstimator):
    """
    The GMMDetector trains a Bayesian Gaussian Mixture Model on a dataset X. Once
    a density is trained we can evaluate the likelihood scores to see if
    it is deemed likely. By giving a threshold this model might then label
    outliers if their likelihood score is too low.

    :param threshold: the limit at which the model thinks an outlier appears, must be between (0, 1)
    :param method: the method that the threshold will be applied to, possible values = [stddev, default=quantile]

    If you select method="quantile" then the threshold value represents the
    quantile value to start calling something an outlier.

    If you select method="stddev" then the threshold value represents the
    numbers of standard deviations before calling something an outlier.

    There are other settings too, these are best described in the BayesianGaussianMixture
    documentation found here:

    https://scikit-learn.org/stable/modules/generated/sklearn.mixture.BayesianGaussianMixture.html.
    """

    _ALLOWED_METHODS = ("quantile", "stddev")

    def __init__(
        self,
        threshold=0.99,
        method="quantile",
        n_components=1,
        covariance_type="full",
        tol=0.001,
        reg_covar=1e-06,
        max_iter=100,
        n_init=1,
        init_params="kmeans",
        weight_concentration_prior_type="dirichlet_process",
        weight_concentration_prior=None,
        mean_precision_prior=None,
        mean_prior=None,
        degrees_of_freedom_prior=None,
        covariance_prior=None,
        random_state=None,
        warm_start=False,
        verbose=0,
        verbose_interval=10,
    ):
        self.threshold = threshold
        self.method = method

        self.n_components = n_components
        self.covariance_type = covariance_type
        self.tol = tol
        self.reg_covar = reg_covar
        self.max_iter = max_iter
        self.n_init = n_init
        self.init_params = init_params
        self.weight_concentration_prior_type = weight_concentration_prior_type
        self.weight_concentration_prior = weight_concentration_prior
        self.mean_precision_prior = mean_precision_prior
        self.mean_prior = mean_prior
        self.degrees_of_freedom_prior = degrees_of_freedom_prior
        self.covariance_prior = covariance_prior
        self.random_state = random_state
        self.warm_start = warm_start
        self.verbose = verbose
        self.verbose_interval = verbose_interval

    def fit(self, X: np.array, y=None) -> "BayesianGMMOutlierDetector":
        """
        Fit the model using X, y as training data.

        :param X: array-like, shape=(n_columns, n_samples,) training data.
        :param y: ignored but kept in for pipeline support
        :return: Returns an instance of self.
        """

        # GMM sometimes throws an error if you don't do this
        X = check_array(X, estimator=self, dtype=FLOAT_DTYPES)
        if len(X.shape) == 1:
            X = np.expand_dims(X, 1)

        if (self.method == "quantile") and (
            (self.threshold > 1) or (self.threshold < 0)
        ):
            raise ValueError(
                f"Threshold {self.threshold} with method {self.method} needs to be 0 < threshold < 1"
            )
        if (self.method == "stddev") and (self.threshold < 0):
            raise ValueError(
                f"Threshold {self.threshold} with method {self.method} needs to be 0 < threshold "
            )
        if self.method not in self._ALLOWED_METHODS:
            raise ValueError(
                f"Method not recognised. Method must be in {self._ALLOWED_METHODS}"
            )

        self.gmm_ = BayesianGaussianMixture(
            n_components=self.n_components,
            covariance_type=self.covariance_type,
            tol=self.tol,
            reg_covar=self.reg_covar,
            max_iter=self.max_iter,
            n_init=self.n_init,
            init_params=self.init_params,
            weight_concentration_prior_type=self.weight_concentration_prior_type,
            weight_concentration_prior=self.weight_concentration_prior,
            mean_precision_prior=self.mean_precision_prior,
            mean_prior=self.mean_prior,
            degrees_of_freedom_prior=self.degrees_of_freedom_prior,
            covariance_prior=self.covariance_prior,
            random_state=self.random_state,
            warm_start=self.warm_start,
            verbose=self.verbose,
            verbose_interval=self.verbose_interval,
        )
        self.gmm_.fit(X)
        score_samples = self.gmm_.score_samples(X)

        if self.method == "quantile":
            self.likelihood_threshold_ = np.quantile(score_samples, 1 - self.threshold)

        if self.method == "stddev":
            density = gaussian_kde(score_samples)
            max_x_value = minimize_scalar(lambda x: -density(x)).x
            mean_likelihood = score_samples.mean()
            new_likelihoods = score_samples[score_samples < max_x_value]
            new_likelihoods_std = np.std(new_likelihoods - mean_likelihood)
            self.likelihood_threshold_ = mean_likelihood - (
                self.threshold * new_likelihoods_std
            )

        return self

    def score_samples(self, X):
        X = check_array(X, estimator=self, dtype=FLOAT_DTYPES)
        check_is_fitted(self, ["gmm_", "likelihood_threshold_"])
        if len(X.shape) == 1:
            X = np.expand_dims(X, 1)

        return self.gmm_.score_samples(X) * -1

    def decision_function(self, X):
        # We subtract self.offset_ to make 0 be the threshold value for being an outlier:
        return self.score_samples(X) + self.likelihood_threshold_

    def predict(self, X):
        """
        Predict if a point is an outlier.
        :param X: array-like, shape=(n_columns, n_samples, ) training data.
        :return: array, shape=(n_samples,) the predicted data. 1 for inliers, -1 for outliers.
        """
        predictions = (self.decision_function(X) >= 0).astype(int)
        predictions[predictions == 1] = -1
        predictions[predictions == 0] = 1
        return predictions

    @property
    def allowed_methods(self):
        warn(
            "Please use `_ALLOWED_METHODS` instead of `allowed_methods`,"
            "`allowed_methods` will be deprecated in future versions",
            DeprecationWarning,
        )
        return self._ALLOWED_METHODS
