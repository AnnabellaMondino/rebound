from ctypes import POINTER, c_int, c_long, c_char_p, byref, pointer
from .simulation import Simulation
from . import clibrebound 
import os
import sys
import math
from collections import Mapping

POINTER_REB_SIM = POINTER(Simulation) 

class SimulationArchive(Mapping):
    """
    SimulationArchive Class.

    This class allows fast access to long running simulations 
    by making use of a SimulationArchive binary file.

    Requirements
    ------------
    The SimulationArchive Class currently only works under the following 
    requirements.  These requirements are not checked for and the user 
    needs to make sure they all apply.

    - Only the WHFast integrator is supported.
    - All symplectic correcters are supported.
    - The simulations must start at t=0.
    - The number of particles can not change.
    - Any additional forces present during the integration also
      need to be present when the SimulationArchive class is used.
    - The ri_whfast.safemode flag may be 0 or 1. However, 
      no manual synchronization steps should be undertaken by the user.


    Examples
    --------
    Here is a simple example:

    >>> sa = rebound.SimulationArchive("archive.bin")
    >>> sim = sa.getSimulation(t=1e6)
    >>> print(sim.particles[1])
    >>> for sim in sa:
    >>>     print(sim.t, sim.particles[1].e)

    """
    def __getitem__(self, key):
        PY3 = sys.version_info[0] == 3
        if PY3:
            int_types = int,
        else:
            int_types = int, long, 

        if isinstance(key, slice):
            raise AttributeError("Slicing not supported due to optimizations.")
        if not isinstance(key, int_types):
            raise AttributeError("Must access individual simulations with integer index.")
        if key < 0:
            key += len(self)
        if key>= len(self):
            raise IndexError("Index out of range, number of blobs stored in binary: %d."%self.Nblob)
        return self.loadFromBlobAndSynchronize(key)

    def loadFromBlobAndSynchronize(self, blob, keep_unsynchronized=1):
        sim = self.simp.contents
        clibrebound.reb_simulationarchive_load_blob.restype = c_int
        retv = clibrebound.reb_simulationarchive_load_blob(self.simp, self.cfilename, c_long(blob))
        if retv:
            raise ValueError("Error while loading blob in binary file. Errorcode: %d."%retv)
        sim.ri_whfast.keep_unsynchronized = keep_unsynchronized
        if self.additional_forces:
            sim.additional_forces = self.additional_forces
        sim.simulationarchive_filename = 0 # Setting this to zero, so no new outputs are generated
        sim.integrator_synchronize()
        return sim

    def __setitem__(self, key, value):
        raise AttributeError("Cannot modify SimulationArchive.")

    def __delitem__(self, key):
        pass

    def __iter__(self):
        for i in range(len(self)):
            yield self[i]

    def __len__(self):
        return self.Nblob

    def __init__(self,filename,additional_forces=None):
        self.additional_forces = additional_forces
        self.cfilename = c_char_p(filename.encode("ascii"))

        # Recreate simulation at t=0
        w = c_int(0)
        clibrebound.reb_create_simulation.restype = POINTER(Simulation)
        simp = clibrebound.reb_create_simulation() 
        clibrebound.reb_create_simulation_from_binary_with_messages(simp, self.cfilename,byref(w))
        if (simp is None) or (w.value & 1):     # Major error
            raise ValueError(BINARY_WARNINGS[0])
        # Note: Other warnings not shown!
        self.simp = simp
        sim = self.simp.contents

        self.filesize = os.path.getsize(filename)
        self.dt = sim.dt
        self.interval = sim.simulationarchive_interval
        self.tmin = 0. # Right now simulations must start at t=0
        self.Nblob = int((self.filesize-sim.simulationarchive_seek_first)/sim.simulationarchive_seek_blob)
        self.tmax = self.tmin + self.interval*(self.Nblob+1)

    def getBlobJustBefore(self, t):
        if t>self.tmax+self.dt or t<self.tmin:
            raise ValueError("Requested time outside of baseline stored in binary fie.")
        bi = max(0,int(math.floor((t-self.dt-self.tmin)/self.interval)))
        bt = self.tmin + self.interval*bi
        return bi, bt

    def getSimulation(self, t, mode='blob', keep_unsynchronized=1):
        """
        Possible values for mode:
         - 'blob' This loads a blob such that sim.t<t.
         - 'close' This integrates the simulation to get to the time t but may overshoot by at most one timestep sim.dt.
         - 'exact' This integrates the simulation to exactly time t. This is not compatible with keep_unsynchronized=1. 
        """
        if mode not in ['blob', 'close', 'exact']:
            raise AttributeError("Unknown mode.")

        bi, bt = self.getBlobJustBefore(t)
        if mode=='blob':
            return self.loadFromBlobAndSynchronize(bi, keep_unsynchronized=keep_unsynchronized)
        else:
            sim = self.simp.contents
            if sim.t<t and bt-sim.dt<sim.t and sim.ri_whfast.keep_unsynchronized==1:
                # Reuse current simulation
                pass
            else:
                # Load from blob
                clibrebound.reb_simulationarchive_load_blob.restype = c_int
                retv = clibrebound.reb_simulationarchive_load_blob(self.simp, self.cfilename, c_long(bi));
                if retv:
                    raise ValueError("Error while loading blob in binary file. Errorcode: %d."%retv)

            if mode=='exact':
                keep_unsynchronized==0
            sim.ri_whfast.keep_unsynchronized = keep_unsynchronized
            if self.additional_forces:
                sim.additional_forces = self.additional_forces
            sim.simulationarchive_filename = 0 # Setting this to zero, so no new outputs are generated
            exact_finish_time = 1 if mode=='exact' else 0
            sim.integrate(t,exact_finish_time=exact_finish_time)
                
            return sim


    def getSimulations(self, times, mode='blob', keep_unsynchronized=1):
        times.sort()
        for t in times:
            yield self.getSimulation(t, mode=mode, keep_unsynchronized=keep_unsynchronized)

    
    def estimateTime(self, t, tbefore=None):
        """
        This function estimates the time needed to integrate the simulation 
        exactly to time the t starting from the nearest blob or the current
        status of the simulation (whichever is smaller).

        If an array is passed as an argument, the function will estimate the
        time it will take to integarte to all the times in the array. The 
        array will be sorted before the estimation. The function assumes
        a simulation can be reused to get to the next requested time if
        this is faster than reloading the simulation from the nearest blob.

        Note that the estimates are based on the runtime of the original 
        simulation. If the original simulation was run on a different 
        machine, the estimated runtime may differ. 
        

        Arguments
        ---------
        t : float, array
            The exact time to which a simulation object is to be integrated.


        Returns
        -------
        An approximation of the runtime required to integrate to time t. 
        
        """
        try:
            # See if we have an array, will fail if not
            iterator = iter(t)
            t.sort()
            tbefore = 0.
            runtime_estimate = 0.
            for _t in t:
                runtime_estimate += self.estimateTime(_t, tbefore)
                tbefore = _t

        except TypeError:
            # t is a single floating point number
            try:
                speed = self.speed
            except AttributeError:
                # get average speed from total runtime:
                sim = self[-1]
                speed = sim.t/sim.simulationarchive_walltime
                # cache speed
                self.speed = speed

            bi, bt = self.getBlobJustBefore(t)
            runtime_estimate = (t-bt)/speed
            if tbefore is not None:
                runtime_estimate = min((t-bt)/speed, (t-tbefore)/speed)

        return runtime_estimate


