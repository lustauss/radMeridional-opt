import numpy as np
import dtOOPythonSWIG as dtOO
import foamlib as fl
import sys
import subprocess
import multiprocessing as mp
import signal
import time
#from utils import * 
import os
import shutil
import traceback
import logging
import glob
logging.basicConfig(
  format='[ %(asctime)s - %(levelname)8s - %(filename)s:%(lineno)d ]'
         ' - %(message)s', 
  datefmt='%d-%b-%y %H:%M:%S', 
  level=logging.DEBUG
)

logging.debug("Debug")
logging.info("Info")
logging.warning("Warning")
logging.error("Error")

import pyDtOO as pd


import numpy as np
import copy

from radmeridional_files.radMeridional import *

class Config():
    """Configure the case variables 

    Attributes
    ----------
    x: List
      List of optimization parameters.
    h_inlet: float
      Inlet height.
    hubCurves: List[analyticCurve]
      List of hub curves.
    shroudCurves: List[analyticCurve]
      List of shroud curves.
    ConfigMerdional: dict
      Configuration dictionary for interfaces.
    ConfigRunner: dict
      Configuration dictionary for runner geometries.
    ConfigGuideVane: dict
      Configuration dictionary for guide vane geometries.

    Examples
    --------

    Parametrizes the hub and shroud contours and creates curve lists.
    Creates the configuration dictionaries as input for the geometry generation.
    Through the methods :meth:`getConfig` and :meth:`getCurves` the Configuration
    Dictionaries as well as the inlet height ``h_inlet`` and the hub and shroud 
    curves can be returned.

    The optimization parameters can be handed to this class through the ``List``
    ``x``.
    
    """
    def __init__(self, x):

        print("Setting up input dictionary")
        
        #
        # Parameters defining the hub and shroud curves
        #
        d_inlet = 2.58
        l_inExt = 0.27
        d_outHub = 0.4
        d_outShroud = 1.885

        l_hub0 = 0.38
        angle_hub0 = 0 * np.pi/180
        l_hub1 = 0.38
        angle_hub1 = 65 * np.pi/180

        l_shroud0 = 0.13
        angle_shroud0 = 0 * np.pi/180
        l_shroud1 = 0.18
        angle_shroud1 = 90 * np.pi/180

        #self.h_inlet = 0.18
        self.h_inlet = 0.36
        h_hub = 0.68
        h_shroud = 0.38

        dx_hub1 = np.cos(angle_hub1)*l_hub1
        dz_hub1 = np.sin(angle_hub1)*l_hub1
        
        # hub curves
        self.hubCurves = [
            dtOO.analyticCurve(
              dtOO.bSplineCurve_pointConstructOCC(
                dtOO.vectorDtPoint3()
                  << dtOO.dtPoint3(+(d_inlet/2 + l_inExt), +0.00, +self.h_inlet)
                  << dtOO.dtPoint3(+d_inlet/2, +0.00, +self.h_inlet),
                1
              ).result()
            ),
            dtOO.analyticCurve(
              dtOO.bSplineCurve_pointConstructOCC(
                dtOO.vectorDtPoint3()
                  << dtOO.dtPoint3(+d_inlet/2, +0.00, +self.h_inlet)
                  << dtOO.dtPoint3(+d_inlet/2-l_hub0, +0.00, +self.h_inlet)
                  << dtOO.dtPoint3(+d_outHub/2+dx_hub1, +0.00, -h_hub+dz_hub1+self.h_inlet)
                  << dtOO.dtPoint3(+d_outHub/2, +0.00, -h_hub+self.h_inlet),
                2
              ).result()
            ),
          ]
        
        # shroud curves
        self.shroudCurves = [
            dtOO.analyticCurve(
              dtOO.bSplineCurve_pointConstructOCC(
                dtOO.vectorDtPoint3()
                  << dtOO.dtPoint3(+(d_inlet/2 + l_inExt), +0.00, +0.00)
                  << dtOO.dtPoint3(+d_inlet/2, +0.00, +0.00),
                1
              ).result()
            ),
            dtOO.analyticCurve(
              dtOO.bSplineCurve_pointConstructOCC(
                dtOO.vectorDtPoint3()
                  << dtOO.dtPoint3(+d_inlet/2, +0.00, +0.00)
                  << dtOO.dtPoint3(+d_inlet/2-l_shroud0, +0.00, +0.00)
                  << dtOO.dtPoint3(+d_outShroud/2, +0.00, -h_shroud+l_shroud1)
                  << dtOO.dtPoint3(+d_outShroud/2, +0.00, -h_shroud),
                2
              ).result()
            ),
            dtOO.analyticCurve(
              dtOO.bSplineCurve_pointConstructOCC(
                dtOO.vectorDtPoint3()
                  << dtOO.dtPoint3(+d_outShroud/2, +0.00, -h_shroud)
                  << dtOO.dtPoint3(+d_outShroud/2, +0.00, -0.54),
                1
              ).result()
            ),
          ]

        self.configMeridional = {
            "label" : "radMeridionalContour",
            
            "interface_hub" : [[1, 0.00],
                               [1, 1.0],],                # [curve, percent]
            "interface_shroud" : [[1, 0.00],
                                  [2, 0.5],],
            "interface_curvature" : [[0.0, 0.5, 1],
                                     [0.0, 0.5, -1],],
        }

        # Straight Guide Vane Configuration
        self.configGuideVane = {
            "label" : "gv",
            "regChannel" : 0,
            "nBlades" : 24,
            
            "offRad" : 1.4125,
            "offAng" : np.pi/180 * -10,
            "alpha" : np.pi/180 * 68,
            "l_tot" : 0.41,
            "ratioL" : 0.485,

            "spanwiseCuts_td" : [0.00, 1.00,],
            "t_le" : [0.0115],
            "u_le" : [0.00],
            "t_mid" : [0.0365],
            "u_mid" : [0.20],
            "t_te" : [0.008],
            "u_te" : [1.00],

            "orientation" : -1,
        }
        # Case - Fitted to blade
        self.configRunner = {
            "label" : "ru",
            "regChannel" : 1,
            "nBlades" : 15,
            
            "spanwiseCuts_mp" : [0.00, 0.33,  0.66, 1.00,],
            #"alpha_1" : [
            #         round((np.pi/180.) * 90., 4),
            #         round((np.pi/180.) * 75., 4),
            #         round((np.pi/180.) * 52., 4)
            #     ],
            #"alpha_2" : [
            #         round((np.pi/180.) * 45., 4),
            #         round((np.pi/180.) * 27., 4),
            #         round((np.pi/180.) * 25., 4),
            #         round((np.pi/180.) * 10., 4)
            #     ],
            #"ratioX" : [
            #         0.65,
            #         0.65,
            #         0.15,
            #         0.24
            #     ],
            #"deltaY" : [
            #         0.80,
            #         0.75,
            #         0.75,
            #         0.53
            #     ],
            "alpha_1" : [
                     round((np.pi/180.) * x[0], 4),
                     round((np.pi/180.) * x[1], 4),
                     round((np.pi/180.) * x[2], 4)
                 ],
            "alpha_2" : [
                     round((np.pi/180.) * x[3], 4),
                     round((np.pi/180.) * x[4], 4),
                     round((np.pi/180.) * x[5], 4),
                     round((np.pi/180.) * x[6], 4)
                 ],
            "ratioX" : [
                     x[7],
                     x[8],
                     x[9],
                     x[10]
                 ],
            "deltaY" : [
                     x[11],
                     x[12],
                     x[13],
                     x[14]
                 ],
            "offX" : [
                     0.125,
                     0.11,
                     0.11,
                     0.005
                 ],
            "offY" : [
                     0.065,
                     0.07,
                     0.035
                 ],

            "spanwiseCuts_td" : [0.00, 1.00,],
            "t_le" : [0.020,0.02],
            "u_le" : [0.00],
            "t_mid" : [0.04,0.03],
            "u_mid" : [0.50],
            "t_te" : [0.01],
            "u_te" : [1.00],

            "adjustRadius" : True,
            "orientation" : 1,

        }
    
    def getConfig(self):
        return self.configMeridional, self.configGuideVane, self.configRunner, self.h_inlet

    def getCurves(self):
        return self.hubCurves, self.shroudCurves


class runRadMeridional:

    def __init__(self, x, state):

        self.state = state
        self.history_ = {}
        self.history_["DateOfBirth"] = time.ctime()
        self.x = x
        # self.mainDir = os.getcwd()
        self.stateNumber = int(self.state.split("_")[-1])
        self.caseName = "of"
        # self.wd = os.environ["TMPDIR"]
        self.wd = "./"
        self.mainDir = self.wd
        os.chdir(self.wd)
    
    #
    # Preparation stage
    #
    def pre(self): 
    
        # Geometry Generation
        # Configure the geometry parameters
        geomConf = Config(self.x)
        configM, configGV, configRu, h_inlet = geomConf.getConfig()
        hubCurves, shroudCurves = geomConf.getCurves()
        
        # Build the geometry model
        model = radMeridional(self.state)
        model.createMeridional(configM, hubCurves, shroudCurves)
        model.createBlade(configGV)
        model.createBlade(configRu)
        
        # openFoam Case Creation
        start_time = time.time()
        logging.info(f"Start Meshing for State {self.state}.")
        
        try:
            # case creation is forked with a timer
            # this is done to prevent getting stuck in gmsh meshing
            run_with_timeout(
                model.createOFCase,
                1800,
                h_inlet
            )
            # applying solver settings
            model.setupSim()
            
            # check if the openfoam case was sucessfully created
            if not (
                os.path.exists("of_" + self.state)
                and os.path.exists("of_" + self.state + "/system")
                and os.path.exists("of_" + self.state + "/constant")
                and os.path.exists("of_" + self.state + "/0")
            ):
                raise ValueError("CFD-Mesh not written for state: ", self.state)
            else:
                logging.info(f"Successfully generated Mesh and Directory for {self.state}.")
            self.history_["DateOfCreation"] = time.ctime()
            self.MeshOk_ = True
        except:
            logging.info(f"Failed Meshing for {self.state}.")
            logging.exception("Exception:")
            logging.info("self.MeshOk_ = False")
            self.MeshOk_ = False
    
    #
    # evaluation stage
    #
    def evaluate(self, *, laminar_end_time=100, end_time=500):
        
        try:
            logging.info(f"POST PROCESSING {self.state}")
            
            # evaluate the simuated case
            evaluation = radMeridional(self.state)
            evaluation.evaluate(end_time)

            if evaluation.isOk_:
                logging.info("StateLabel = %s -> OK", self.state)
            else:
                logging.info("StateLabel = %s -> FAIL", self.state)
                pass
            fit, fit_extra = evaluation.GiveFitness()
            logging.info(f"FITNESS of {self.state}: {fit}")
        except:
            logging.exception("Evaluation Exception")
            raise
        return fit, fit_extra
    
    # delete case data
    def delete(self):
        cleanup(
            self.state,
            case=self.caseName,
        )

    def get_history(self):
        return self.history_

#
# run a function forked with a timeout
#
def run_with_timeout(func, timeout, *args, **kwargs):
    pid = os.fork()

    if pid == 0:
        # Child process
        try:
            func(*args, **kwargs)
            os._exit(0)
        except Exception:
            logging.exception("Exception in child process")
            os._exit(1)

    # Parent process
    start = time.time()

    while True:
        finished_pid, status = os.waitpid(pid, os.WNOHANG)

        if finished_pid == pid:
            if os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0:
                return

            raise RuntimeError("Child process failed")

        if time.time() - start >= timeout:
            logging.error(
                f"Process {pid} exceeded timeout of {timeout} seconds. Killing it."
            )

            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)  # reap child

            raise TimeoutError(
                f"{func.__name__} exceeded timeout of {timeout} seconds"
            )

        time.sleep(0.1)

def cleanup(state, case="of", log_errors=True):
    """Delete generated files for one state while retaining staged assets."""
    try:
        fileList = glob.glob(state + ".*", recursive=False)
        fileList = fileList + glob.glob(state + "_*", recursive=False)
        fileList = fileList + glob.glob("dtMeshGRegion_*", recursive=False)
        for i in ["_"]:
            fileList.append(case + i + state)
        for filePath in fileList:
            try:
                os.remove(filePath)
            except IsADirectoryError:
                shutil.rmtree(filePath)
    except Exception as e:
        if log_errors:
            logging.info("Catch exception in delete: %s", e)

# ----------------------------------- EOF ----------------------------------- #
