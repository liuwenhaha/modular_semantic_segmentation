#!/usr/bin/python
#
# A library for finding the optimal dirichlet prior from counts
# By: Max Sklar
# @maxsklar
# https://github.com/maxsklar

# Copyright 2013 Max Sklar

import math
import logging
import random
import scipy.special as mathExtra
import scipy
import numpy as np

def digamma(x): return mathExtra.psi(x)
def trigamma(x): return mathExtra.polygamma(1, x)


# Find the "sufficient statistic" for a group of multinomials.
# Essential, it's the average of the log probabilities
def getSufficientStatistic(multinomials):
  N = len(multinomials)
  K = len(multinomials[0])

  retVal = [0]*K

  for m in multinomials:
    for k in range(0, K):
      retVal[k] += math.log(m[k])

  for k in range(0, K): retVal[k] /= N
  return retVal

# Find the log probability of the data for a given dirichlet
# This is equal to the log probabiliy of the data.. up to a linear transform
def logProbForMultinomials(alphas, ss, delta):
  alpha_sum = np.sum(alphas)
  retVal = mathExtra.gammaln(alpha_sum)
  retVal -= np.sum(mathExtra.gammaln(alphas))
  retVal += np.sum(np.multiply(alphas, ss))
  retVal -= delta * np.square(alphas).sum()
  return retVal

#Gives the derivative with respect to the log of prior.  This will be used to adjust the loss
def getGradientForMultinomials(alphas, ss, delta):
  K = len(alphas)
  C = digamma(sum(alphas)) # - DELTA  * sum(alphas)
  retVal = [C]*K
  for k in range(0, K):
    retVal[k] += ss[k] - digamma(alphas[k]) - 2 * delta * alphas[k]


  return retVal

#The hessian is actually the sum of two matrices: a diagonal matrix and a constant-value matrix.
#We'll write two functions to get both
def priorHessianConst(alphas, ss, delta): return -trigamma(sum(alphas)) + 2 * delta
def priorHessianDiag(alphas, ss): return [trigamma(a) for a in alphas]

# Compute the next value to try here
# http://research.microsoft.com/en-us/um/people/minka/papers/dirichlet/minka-dirichlet.pdf (eq 18)
def getPredictedStep(hConst, hDiag, gradient):
  K = len(gradient)
  numSum = 0.0
  for i in range(0, K):
    numSum += gradient[i] / hDiag[i]

  denSum = 0.0
  for i in range(0, K): denSum += 1.0 / hDiag[i]

  b = numSum / ((1.0/hConst) + denSum)

  retVal = [0]*K
  for i in range(0, K): retVal[i] = (b - gradient[i]) / hDiag[i]
  return retVal

# Uses the diagonal hessian on the log-alpha values
def getPredictedStepAlt(hConst, hDiag, gradient, alphas):
  K = len(gradient)

  Z = 0
  for k in range(0, K):
    Z += alphas[k] / (gradient[k] - alphas[k]*hDiag[k])
  Z *= hConst

  Ss = [0]*K
  for k in range(0, K):
    Ss[k] = 1.0 / (gradient[k] - alphas[k]*hDiag[k]) / (1 + Z)
  S = sum(Ss)

  retVal = [0]*K
  for i in range(0, K):
    retVal[i] = gradient[i] / (gradient[i] - alphas[i]*hDiag[i]) * (1 - hConst * alphas[i] * S)

  return retVal

#The priors and data are global, so we don't need to pass them in
def getTotalLoss(trialPriors, ss, delta):
  return -1*logProbForMultinomials(trialPriors, ss, delta)

def predictStepUsingHessian(gradient, priors, ss, delta):
	totalHConst = priorHessianConst(priors, ss, delta)
	totalHDiag = priorHessianDiag(priors, ss)
	return getPredictedStep(totalHConst, totalHDiag, gradient)

def predictStepLogSpace(gradient, priors, ss, delta):
	totalHConst = priorHessianConst(priors, ss, delta)
	totalHDiag = priorHessianDiag(priors, ss)
	return getPredictedStepAlt(totalHConst, totalHDiag, gradient, priors)


# Returns whether it's a good step, and the loss
def testTrialPriors(trialPriors, ss, delta):
	for alpha in trialPriors:
		if alpha <= 0:
			return float("inf")

	return getTotalLoss(trialPriors, ss, delta)

def sqVectorSize(v):
	s = 0
	for i in range(0, len(v)): s += v[i] ** 2
	return s

def findDirichletPriors(ss, initAlphas, max_iter=1000, delta=1e-2):
  priors = initAlphas

  # Let the learning begin!!
  #Only step in a positive direction, get the current best loss.
  currentLoss = getTotalLoss(priors, ss, delta)

  gradientToleranceSq = 2 ** -20
  learnRateTolerance = 2 ** -10

  count = 0
  while(count < max_iter):
    count += 1

    #Get the data for taking steps
    gradient = getGradientForMultinomials(priors, ss, delta)
    gradientSize = sqVectorSize(gradient)
    #print(count, "Loss: ", currentLoss, ", Priors: ", priors, ", Gradient Size: ", gradientSize, gradient)

    if (gradientSize < gradientToleranceSq):
      #print("Converged with small gradient")
      return priors

    trialStep = predictStepUsingHessian(gradient, priors, ss, delta)

    #First, try the second order method
    trialPriors = [0]*len(priors)
    for i in range(0, len(priors)): trialPriors[i] = priors[i] + trialStep[i]

    loss = testTrialPriors(trialPriors, ss, delta)
    if loss < currentLoss:
      currentLoss = loss
      priors = trialPriors
      continue

    trialStep = predictStepLogSpace(gradient, priors, ss, delta)
    trialPriors = [0]*len(priors)
    for i in range(0, len(priors)): trialPriors[i] = priors[i] * math.exp(trialStep[i])
    loss = testTrialPriors(trialPriors, ss, delta)

    #Step in the direction of the gradient until there is a loss improvement
    loss = 10000000
    learnRate = 1.0
    while loss > currentLoss:
      learnRate *= 0.9
      trialPriors = [0]*len(priors)
      for i in range(0, len(priors)): trialPriors[i] = priors[i] + gradient[i]*learnRate
      loss = testTrialPriors(trialPriors, ss, delta)

    if (learnRate < learnRateTolerance):
      #print("Converged with small learn rate")
      return priors

    currentLoss = loss
    priors = trialPriors

  #print("Reached max iterations")
  return priors

def findDirichletPriorsFromMultinomials(multinomials, initAlphas):
	ss = getSufficientStatistic(multinomials)
	return findDirichletPriors(ss, initAlphas)
