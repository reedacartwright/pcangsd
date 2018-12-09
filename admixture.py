"""
Estimate admixture using Non-negative Matrix Factorization based on multiplicative updates.
"""

__author__ = "Jonas Meisner"

# Import libraries
import numpy as np
import threading
from numba import jit
from helpFunctions import frobenius, frobenius2d_multi, rmse2d_float32
from math import log

##### Functions #####
# Estimate log likelihood of ngsAdmix model (inner)
@jit("void(f4[:, :], f4[:, :], i8, i8, f8[:])", nopython=True, nogil=True, cache=True)
def logLike_admixInner(likeMatrix, Pi, S, N, L):
	m, n = Pi.shape

	for ind in xrange(S, min(S+N, m)):
		for s in xrange(n):
			like0 = likeMatrix[3*ind, s]*(1 - Pi[ind, s])*(1 - Pi[ind, s])
			like1 = likeMatrix[3*ind+1, s]*2*Pi[ind, s]*(1 - Pi[ind, s])
			like2 = likeMatrix[3*ind+2, s]*Pi[ind, s]*Pi[ind, s]
			L[ind] += log(like0 + like1 + like2)

# Estimate log likelihood of ngsAdmix model (outer)
def logLike_admix(likeMatrix, Pi, chunks, chunk_N):
	m, n = likeMatrix.shape
	m /= 3
	logLike_inds = np.zeros(m) # Log-likelihood container for each individual

	# Multithreading
	threads = [threading.Thread(target=logLike_admixInner, args=(likeMatrix, Pi, chunk, chunk_N, logLike_inds)) for chunk in chunks]
	for thread in threads:
		thread.start()
	for thread in threads:
		thread.join()

	return np.sum(logLike_inds)

# Update factor matrices
@jit("void(f4[:, :], f4[:, :], f4[:, :])", nopython=True, nogil=True, cache=True)
def updateF(F, A, FB):
	n, K = F.shape
	for s in xrange(n):
		for k in xrange(K):
			F[s, k] *= A[s, k]/FB[s, k]
			F[s, k] = max(F[s, k], 1e-4)
			F[s, k] = min(F[s, k], 1-(1e-4))

@jit("void(f4[:, :], f4[:, :], f4[:, :], f8)", nopython=True, nogil=True, cache=True)
def updateQ(Q, A, QB, alpha):
	m, K = Q.shape
	for i in xrange(m):
		for k in xrange(K):
			Q[i, k] *= A[i, k]/(QB[i, k] + alpha)
			Q[i, k] = max(Q[i, k], 1e-4)
			Q[i, k] = min(Q[i, k], 1-(1e-4))

# Estimate admixture using non-negative matrix factorization
def admixNMF(X, K, likeMatrix, alpha=0, iter=100, tole=5e-5, seed=0, batch=5, threads=1):
	m, n = X.shape # Dimensions of individual allele frequencies

	# Shuffle individual allele frequencies
	np.random.seed(seed) # Set random seed
	shuffleX = np.random.permutation(n)
	X = X[:, shuffleX]

	# Initiate matrices
	Q = np.random.rand(m, K).astype(np.float32, copy=False)
	Q /= np.sum(Q, axis=1, keepdims=True)
	prevQ = np.copy(Q)
	F = np.dot(np.dot(np.linalg.inv(np.dot(Q.T, Q)), Q.T), X).T

	# Multithreading parameters
	chunk_N = int(np.ceil(float(m)/threads))
	chunks = [i * chunk_N for i in xrange(threads)]

	# Batch preparation
	batch_N = int(np.ceil(float(n)/batch))
	bIndex = np.arange(0, n, batch_N)

	# SG-MU
	for iteration in xrange(1, iter + 1):
		for b in bIndex:
			bEnd = min(b + batch_N, n)
			Xbatch = X[:, b:bEnd]
			Fbatch = F[b:bEnd]
			nInner = Xbatch.shape[1]
			pF = 2*(1 + (m*nInner + m*K)/(nInner*K + nInner))
			pQ = 2*(1 + (m*nInner + nInner*K)/(m*K + m))

			# Update F
			A = np.dot(Xbatch.T, Q)
			B = np.dot(Q.T, Q)
			for inner in xrange(pF): # Acceleration updates
				F_prev = np.copy(Fbatch)
				updateF(Fbatch, A, np.dot(Fbatch, B))

				if inner == 0:
					F_init = frobenius(Fbatch, F_prev)
				else:
					if (frobenius(Fbatch, F_prev) <= (0.1*F_init)):
						break

			# Update Q
			A = np.dot(Xbatch, Fbatch)
			B = np.dot(Fbatch.T, Fbatch)
			for inner in xrange(pQ): # Acceleration updates
				Q_prev = np.copy(Q)
				updateQ(Q, A, np.dot(Q, B), alpha)
				Q /= np.sum(Q, axis=1, keepdims=True)

				if inner == 0:
					Q_init = frobenius(Q, Q_prev)
				else:
					if (frobenius(Q, Q_prev) <= (0.1*Q_init)):
						break

		# Measure difference
		diff = rmse2d_float32(Q, prevQ)
		print "CSG-MU (" + str(iteration) + "). Q-RMSD=" + str(diff)

		if diff < tole:
			print "CSG-MU has converged."
			break
		prevQ = np.copy(Q)

	del prevQ, A, B, F_prev, Q_prev

	# Reshuffle columns
	F = F[np.argsort(shuffleX)]
	X = X[:, np.argsort(shuffleX)]

	# Frobenius and log-like
	Pi = np.dot(Q, F.T) # Individual allele frequencies from admixture estimates
	Pi.clip(min=1e-4, max=1-(1e-4), out=Pi)
	Obj = frobenius2d_multi(X, Pi, chunks, chunk_N)
	print "Frobenius error: " + str(Obj)

	logLike = logLike_admix(likeMatrix, Pi, chunks, chunk_N) # Log-likelihood (ngsAdmix model)
	print "Log-likelihood: " + str(logLike)
	return Q, F, logLike

# Automatic search for appropriate alpha
def alphaSearch(aEnd, depth, indF, K, likeMatrix, iter, tole, seed, batch, t):
	# First search
	aMin = 0
	aMax = aEnd
	aMid = (aMin + aMax)/2.0
	aStep = (aMin + aMax)/4.0

	print "NMF: K=" + str(K) + ", alpha=" + str(aMin) + ", batch=" + str(batch) + " and seed=" + str(seed)
	Q_best, F_best, L_best = admixNMF(indF, K, likeMatrix, aMin, iter, tole, seed, batch, t)
	argL = 0
	aBest = aMin
	
	print "\nNMF: K=" + str(K) + ", alpha=" + str(aMid) + ", batch=" + str(batch) + " and seed=" + str(seed)
	Q_test, F_test, L_test = admixNMF(indF, K, likeMatrix, aMid, iter, tole, seed, batch, t)
	if L_test > L_best:
		Q_best, F_best, L_best = np.copy(Q_test), np.copy(F_test), L_test
		argL = 1
		aBest = aMid
	
	print "\nNMF: K=" + str(K) + ", alpha=" + str(aMax) + ", batch=" + str(batch) + " and seed=" + str(seed)
	Q_test, F_test, L_test = admixNMF(indF, K, likeMatrix, aMax, iter, tole, seed, batch, t)
	if L_test > L_best:
		Q_best, F_best, L_best = np.copy(Q_test), np.copy(F_test), L_test
		argL = 2
		aBest = aMax

	if argL == 0:
		aMax = aMid
		aMid = aMax/2.0
	else:
		aMid = [aMin, aMid, aMax][argL]
		aMin = aMid - aStep
		aMax = aMid + aStep

	for d in range(2, depth+1):
		print "\nDepth=" + str(d) + ", best alpha=" + str(aBest)
		if aMin == 0:
			print "\n" + "NMF: K=" + str(K) + ", alpha=" + str(aMid) + ", batch=" + str(batch) + " and seed=" + str(seed)
			Q_test, F_test, L_test = admixNMF(indF, K, likeMatrix, aMid, iter, tole, seed, batch, t)
			if L_test > L_best:
				Q_best, F_best, L_best = np.copy(Q_test), np.copy(F_test), L_test
				argL = 1
				aBest = aMid

		else:
			print "\nNMF: K=" + str(K) + ", alpha=" + str(aMin) + ", batch=" + str(batch) + " and seed=" + str(seed)
			Q_test, F_test, L_test = admixNMF(indF, K, likeMatrix, aMin, iter, tole, seed, batch, t)
			if L_test > L_best:
				Q_best, F_best, L_best = np.copy(Q_test), np.copy(F_test), L_test
				argL = 0
				aBest = aMin

			else:
				print "\nNMF: K=" + str(K) + ", alpha=" + str(aMax) + ", batch=" + str(batch) + " and seed=" + str(seed)
				Q_test, F_test, L_test = admixNMF(indF, K, likeMatrix, aMax, iter, tole, seed, batch, t)
				if L_test > L_best:
					Q_best, F_best, L_best = np.copy(Q_test), np.copy(F_test), L_test
					argL = 2
					aBest = aMax
				else:
					argL = 1

		aStep /= 2.0
		if aMin == 0:
			aMax = aMid
			aMid = aMax/2.0
		else:
			aMid = [aMin, aMid, aMax][argL]
			aMin = aMid - aStep
			aMax = aMid + aStep

	return Q_best, F_best, aBest