#    This file is part of EAP.
#
#    EAP is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Lesser General Public License as
#    published by the Free Software Foundation, either version 3 of
#    the License, or (at your option) any later version.
#
#    EAP is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Lesser General Public License for more details.
#
#    You should have received a copy of the GNU Lesser General Public
#    License along with EAP. If not, see <http://www.gnu.org/licenses/>.

#    Special thanks to Nikolaus Hansen for providing major part of 
#    this code. The CMA-ES algorithm is provided in many other languages
#    and advanced versions at http://www.lri.fr/~hansen/cmaesintro.html.

"""A module that provides support for the Covariance Matrix Adaptation 
Evolution Strategy.
"""

import logging
from math import sqrt, cos, log, pi
import numpy
import random   # Only used to seed numpy.random
import sys      # Used to get maxint

numpy.random.seed(random.randint(0, sys.maxint))

_logger = logging.getLogger("eap.cma")
    
def esCMA(toolbox, population, ngen, halloffame=None, statistics=None):
    """The CMA-ES algorithm as described in Hansen, N. (2006). *The CMA
    Evolution Strategy: A Comparing Rewiew.*
    
    The provided *population* should be a list of one or more individuals. The
    other keyword arguments are passed to the class
    :class:`~eap.cma.CMAStrategy`.
    """
    _logger.info("Start of evolution")
        
    for g in xrange(ngen):
        _logger.info("Evolving generation %i", g)
        
        # Evaluate the individuals
        for ind in population:
            ind.fitness.values = toolbox.evaluate(ind)
        
        if halloffame is not None:
            halloffame.update(population)
        
        # Update the Strategy with the evaluated individuals
        toolbox.update(population)
        
        if statistics is not None:
            statistics.update(population)
            for key, stat in statistics.data.items():
                _logger.debug("%s %s" % (key, stat[-1][0]))

    _logger.info("End of (successful) evolution")

class CMAStrategy(object):
    """
    Additional configuration may be passed through the *params* argument as a 
    dictionary,
    
    +----------------+---------------------------+----------------------------+
    | Parameter      | Default                   | Details                    |
    +================+===========================+============================+
    | ``lambda_``    | ``floor(4 + 3 * log(N))`` | Number of children to      |
    |                |                           | produce at each generation,|
    |                |                           | ``N`` is the individual's  |
    |                |                           | size.                      |
    +----------------+---------------------------+----------------------------+
    | ``mu``         | ``floor(lambda_ / 2)``    | The number of parents to   | 
    |                |                           | keep from the              |
    |                |                           | lambda children.           |
    +----------------+---------------------------+----------------------------+
    | ``weights``    | ``"superlinear"``         | Decrease speed, can be     |
    |                |                           | ``"superlinear"``,         |
    |                |                           | ``"linear"`` or            |
    |                |                           | ``"equal"``.               |
    +----------------+---------------------------+----------------------------+
    | ``cs``         | ``(mueff + 2) /           | Cumulation constant for    |
    |                | (N + mueff + 3)``         | step-size.                 |
    +----------------+---------------------------+----------------------------+
    | ``damps``      | ``1 + 2 * max(0, sqrt((   | Damping for step-size.     |
    |                | mueff - 1) / (N + 1)) - 1)|                            |
    |                | + cs``                    |                            |
    +----------------+---------------------------+----------------------------+
    | ``ccum``       | ``4 / (N + 4)``           | Cumulation constant for    |
    |                |                           | covariance matrix.         |
    +----------------+---------------------------+----------------------------+
    | ``ccov1``      | ``2 / ((N + 1.3)^2 +      | Learning rate for rank-one |
    |                | mueff)``                  | update.                    |
    +----------------+---------------------------+----------------------------+
    | ``ccovmu``     | ``2 * (mueff - 2 + 1 /    | Learning rate for rank-mu  |
    |                | mueff) / ((N + 2)^2 +     | update.                    |
    |                | mueff)``                  |                            |
    +----------------+---------------------------+----------------------------+
    """
    def __init__(self, centroid, sigma, **kargs):
        self.params = kargs
        
        # Create a centroid as a numpy array
        self.centroid = numpy.array(centroid)
        
        self.dim = len(self.centroid)
        self.sigma = sigma
        self.pc = numpy.zeros(self.dim)
        self.ps = numpy.zeros(self.dim)
        self.chiN = sqrt(self.dim) * (1 - 1. / (4. * self.dim) + \
                                      1. / (21. * self.dim**2))
        
        self.B = numpy.identity(self.dim)
        self.C = numpy.identity(self.dim)
        self.diagD = numpy.ones(self.dim)
        self.BD = self.B * self.diagD

        self.cond = 1       
 
        self.lambda_ = self.params.get("lambda_", int(4 + 3 * log(self.dim)))
        
        self.update_count = 0
        
        self.computeParams(self.params)
        
    def generate(self, ind_init):
        """Generate a population from the current strategy using the 
        centroid individual as parent.
        """
        arz = numpy.random.randn(self.lambda_, self.dim)
        return [ind_init(self.centroid + self.sigma * numpy.dot(self.BD, arzi)) for arzi in arz]
        
    def update(self, population):
        """Update the current covariance matrix strategy.
        """
        population.sort(key=lambda ind: ind.fitness, reverse=True)
        
        old_centroid = self.centroid
        self.centroid = numpy.dot(self.weights, population[0:self.mu])
        
        c_diff = self.centroid - old_centroid
        
        # Cumulation : update evolution path
        self.ps = (1 - self.cs) * self.ps \
             + sqrt(self.cs * (2 - self.cs) * self.mueff) / self.sigma \
             * numpy.dot(self.B, (1. / self.diagD) \
                          * numpy.dot(self.B.T, c_diff))
        
        hsig = numpy.linalg.norm(self.ps) \
               / sqrt(1 - (1 - self.cs)**(2 * self.update_count)) \
               / self.chiN < 1.4 + 2 / (self.dim + 1)
               
        self.update_count += 1
               
        self.pc = (1 - self.cc) * self.pc \
             + hsig * (sqrt(self.cc * (2 - self.cc) * self.mueff) / \
                     self.sigma) * c_diff
        
        # Update covariance matrix
        artmp = population[0:self.mu] - old_centroid
        self.C = (1 - self.ccov1 - self.ccovmu + (1 - hsig) \
                   * self.ccov1 * self.cc * (2 - self.cc)) * self.C \
                 + numpy.outer(self.ccov1 * self.pc, self.pc) \
                 + self.ccovmu \
                   * numpy.dot(artmp.T , (self.weights * artmp.T).T) \
                   / self.sigma**2
        
        self.sigma *= numpy.exp((numpy.linalg.norm(self.ps) / self.chiN - 1.) \
                                * self.cs / self.damps)
        
        self.diagD, self.B = numpy.linalg.eigh(self.C)
        indx = numpy.argsort(self.diagD)

        self.cond = self.diagD[indx[-1]]/self.diagD[indx[0]]

        self.diagD = self.diagD[indx]**0.5
        self.B = self.B[:,indx]
        self.BD = self.B * self.diagD
        
        arz = numpy.random.randn(self.lambda_, self.dim)
        for ind, arzi in zip(population, arz):
            del ind[:]
            ind.extend(self.centroid + self.sigma * numpy.dot(self.BD, arzi))

    def computeParams(self, params):
        """Those parameters depends on lambda and need to computed again if it 
        changes during evolution.
        """
        self.mu = params.get("mu", self.lambda_ / 2)
        rweights = params.get("weights", "superlinear")
        if rweights == "superlinear":
            self.weights = log(self.mu + 0.5) - \
                        numpy.log(numpy.arange(1, self.mu + 1))
        elif rweights == "linear":
            self.weights = self.mu + 0.5 - numpy.arange(1, self.mu + 1)
        elif rweights == "equal":
            self.weights = numpy.ones(self.mu)
        else:
            pass    # Print some warning ?
        
        self.weights /= sum(self.weights)
        self.mueff = 1. / sum(self.weights**2)
        
        self.cc = params.get("ccum", 4. / (self.dim + 4.))
        self.cs = params.get("cs", (self.mueff + 2.) / 
                                   (self.dim + self.mueff + 3.))
        self.ccov1 = params.get("ccov1", 2. / ((self.dim + 1.3)**2 + \
                                         self.mueff))
        self.ccovmu = params.get("ccovmu", 2. * (self.mueff - 2. +  \
                                                 1. / self.mueff) / \
                                           ((self.dim + 2.)**2 + self.mueff))
        self.ccovmu = min(1 - self.ccov1, self.ccovmu)
        self.damps = 1. + 2. * max(0, sqrt((self.mueff - 1.) / \
                                            (self.dim + 1.)) - 1.) + self.cs
        self.damps = params.get("damps", self.damps)
        

def rand(individual):
    """Random test objective function."""
    return numpy.random.random()
    
def plane(individual):
    """Plane test objective function."""
    return individual[0]

def rastrigin(individual):
    """Rastrigin test objective function. Consider using ``lambda_ = 20 * N`` 
    for this test function.
    """
    return 10 * len(individual) + sum(gene * gene - 10 * \
                        cos(2 * pi * gene) for gene in individual)
    
def sphere(individual):
    """Sphere test objective function."""
    return sum(gene * gene for gene in individual)

def cigar(individual):
    """Cigar test objective function."""
    return individual[0]**2 + 1e6 * sum(gene * gene for gene in individual)

def rosenbrock(individual):  
    """Rosenbrock test objective function."""
    return sum(100 * (x * x - y)**2 + (1. - x)**2 \
                   for x, y in zip(individual[:-1], individual[1:]))
    
