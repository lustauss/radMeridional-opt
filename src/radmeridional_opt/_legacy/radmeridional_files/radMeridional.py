

import logging

if not logging.getLogger().handlers:
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

import foamlib
from pyDtOO import *
import dtOOPythonSWIG as dtOO

import shutil
import time
from pathlib import Path
import re
import numpy as np
import sys
import os
import importlib
from typing import List


class radMeridional:
    
    """Create geometries and meshes of a radial flow machine.
     
    Attributes
    ----------
    container: dtBundle
      Initialization of the dtBundle.
    bC: baseContainer
      dtOO base container.
    cV: lvH_constValue
      Labeled vector handling of constant values.
    aF: lvH_analyticFunction
      Labeled vector handling of analytic functions.
    aG: lvH_analyticGeometry
      Labeled vector handling of analytic geometries.
    bV: lvH_boundedVolume
      Labeled vector handling of bounded volumes.
    dC: lvh_dtCase
      Labeled vector handling of cases.
    dP: lvH_dtPlugin
      Labeled vector handling of plugins.
    radMeridionalContour: analyticGeometry_piecewiseMeridionalRotContour
      Object that creates the meridional contour.

    Examples
    --------

    """
	
    def __init__(
        self,
        state = None
    ):
        """Initalize the radMeridional object. 

        This constructor:
        - Creates the main dtOO container
        - Initializes logging
        - Configures static dtOO properties
        - Sets up base container and vector handlers
        - Initializes labeled vector handling objects (bC, cV, aF, aG, bV, dC, dP)
        
        Parameters
        ----------
        None

        Returns
        -------
        None

        """ 
        # Create an empty container
        self.container = dtOO.dtBundle()
        
        # Create log file
        if state != None:
            self.state_ = state
            dtOO.logMe.initLog('build.'+self.state_+'.log')
           
            ### change working directory to local ssd ###
            self.wd_ = "./"
            #os.chdir(self.wd_)
            
            #working_dir =f'{{\"name\": \"workingDirectory\", \"value\": \"{self.wd_}\" }}'
            
            self.cDir_ = os.path.join(self.wd_, "of_"+state)
            logging.info(f"case directory: {self.cDir_}")
            
            #self.history_ = {}

            #### change working directory to local ssd ###
            #wd = os.environ["TMPDIR"]
            #os.chdir(wd)
            
            #working_dir =f'{{"name": "workingDirectory", "value": "{wd}" }},'
            ##working_dir =f'{{\"name\": \"workingDirectory\", \"value\": \"{wd}\" }}'
        
        else:
            dtOO.logMe.initLog('build.log')
        working_dir = ""

        # Init staticProperties
        dtOO.staticPropertiesHandler.getInstance().jInit(
          dtOO.jsonPrimitive(
            '{'
              '"option" : ['
                '{"name" : "invY_precision", "value" : "1.e-04"},'
                '{"name" : "xyz_resolution", "value" : "1.e-04"},'
                '{"name" : "uvw_resolution", "value" : "1.e-03"},'
                '{"name" : "function_render_resolution_u", "value" : "150"},'
                '{"name" : "function_render_resolution_v", "value" : "150"},'
                '{"name" : "function_render_resolution_w", "value" : "150"},'
                '{"name" : "geometry_render_resolution_u", "value" : "150"},'
                '{"name" : "geometry_render_resolution_v", "value" : "150"},'
                '{"name" : "geometry_render_resolution_w", "value" : "150"},'
                '{"name" : "ompNumThreads", "value" : "2"},'
                '{"name" : "map1dTo3d_deltaPer", "value" : "0.01"},'
                '{"name" : "map2dTo3d_deltaPer", "value" : "0.01"},'
                '{"name" : "map3dTo3d_deltaPer", "value" : "0.01"},'
                '{"name" : "isEqualExtendCheck", "value" : "true"},'
                + working_dir +
                '{"name" : "logLevel", "value" : "2"}'
                #'{"name" : "logLevel", "value" : "99"}'
              ']'
            '}'
          )
        )
        self.aF = self.container.cptr_aF()
        self.aG = self.container.cptr_aG()
        self.bV = self.container.cptr_bV()
        self.dC = self.container.cptr_dC()
        self.dP = self.container.cptr_dP()

        # Init baseContainer and labeledVectorHandlings
        self.bC = self.container.cptr_bC()
        self.cV = self.container.cptr_cV()

        self.cV.push_back(
            dtOO.sliderFloatParam("QIn", 0.5, 0.0, 1.0).clone()
        )
        # clearing prevents segmentation fault
        dtOO.lVHOstateHandler.clear()
        dtOO.lVHOstateHandler( dtOO.jsonPrimitive(), self.cV ).thisown = False



    def createMeridional(self, configM, hubCurves, shroudCurves): 
        """Create the regular channels and special hub and shroud curves.

        This method:
        
            - Splits the hub and shroud curves at the interfaces.
            - Creates the interface curves.
            - Creates regular channels between the inlet and the interfaces.
            - Creates the special hub and shroud curves after the last interface.

        Parameters
        ----------
        configM : dict
          Dictionary containing the interface parameters with the
          following keys:

          - **label** (*str*):
            Label.

          - **interface_hub** (*List[Tuple[int, float]]*):
            Positions of the interfaces on the hub curves.
            Each entry represents:

              - ``interface_hub[i]``: Interface number
              - ``interface_hub[i][0]``: Curve number where the interface is located
              - ``interface_hub[i][1]``: Percentage along the curve (0 to 1)

          - **interface_shroud** (*List[Tuple[int, float]]*):
            Positions of the interfaces on the shroud curves.
            Each entry represents:

              - ``interface_shroud[i]``: Interface number
              - ``interface_shroud[i][0]``: Curve number where the interface is located
              - ``interface_shroud[i][1]``: Percentage along the curve (0 to 1)

          - **interface_curvature** (*List[Tuple[float, float, int]]*):
            Curvature of the interface curve from hub to shroud.
            Each entry represents:

              - ``interface_curvature[i]``: Interface number
              - ``interface_curvature[i][0]``: Curvature offset point [%] from hub to shroud
              - ``interface_curvature[i][1]``: Curvature as a percentage of the connection line length
              - ``interface_curvature[i][2]``: Curvature direction

        hubCurves : List[analyticGeometry]
          List of hub curves.

        shroudCurves : List[analyticGeometry]
          List of shroud curves.

        Returns
        -------
        None
        """
        
        #
        # Create the interface curves and the regular channels as well as the special 
        # hub and shroud curves.
        # The radMeridionalContour object is used in the other methods to return the 
        # geometries.
        #
        from dtOOPythonApp.builder import analyticGeometry_piecewiseMeridionalRotContour
        self.radMeridionalContour = analyticGeometry_piecewiseMeridionalRotContour( 
          label = configM["label"],
          hubCurves = hubCurves,
          shroudCurves = shroudCurves,
          interface_hub = configM["interface_hub"],
          interface_shroud = configM["interface_shroud"],
          interface_curvature = configM["interface_curvature"],
        ).enableDebug()
        self.container = self.radMeridionalContour.buildExtract(self.container)
    
    def createLayerRegion(self, configL):
        """Create a layered flow channel geometry.

        This method:

            - Takes the special hub and shroud curves from the ``radMeridionalContour`` object.
            - Creates transfinite faces on the hub and shroud curves.
            - Creates a multiple bounded volume inside the flow channel.
            - Applies mesh settings to the geometry regions.

        Parameters
        ----------
        configL : dict
          Dictionary containing the parameters for the layers with the
          following keys:

          - **label** (*str*):
            Label.

          - **nSlices** (*int*):
            Number of total slices. The geometry spans 360° / nSlices.

          - **layer_thickness** (*float*):
            Thickness of the layers on the hub and shroud curves.

          - **layer_supports** (*List[float]*):
            Number and positions of layer support points on each hub and shroud curve.

        Returns
        -------
        None 
        """

        #
        # Return the special hub and shroud curves and inlet and outlet curves
        # of the layered region from the radMeridionalContour object, which was 
        # created in the createMeridional method.
        #
        speHub, speShroud, inOutCurves = self.radMeridionalContour.getLayerRegionCurves()
        
        #
        # Build the layer region geometry as transfinite layers and 
        # a multiple bounded volume
        #
        from dtOOPythonApp.builder import analyticGeometry_layerRegion
        layerRegion = analyticGeometry_layerRegion( 
          label = configL["label"],
          speHub = speHub,
          speShroud = speShroud,
          inOutCurves = inOutCurves,
          layer_thickness = configL["layer_thickness"],
          layer_supports = configL["layer_supports"],
        ).enableDebug()#.buildExtract( self.container )
        self.container = layerRegion.buildExtract(self.container)
        
        #
        # Apply mesh settings to the layer region
        #
        
        #
        # Return  the data of the layers a nested list with the following format:
        # layers = Tuple[
        #     Tuple[
        #         List[analyticGeometry], List[bool]
        #     ], 
        #     Tuple[
        #         List[analyticGeometry], List[bool]
        #     ]
        # ]
        # with:
        # layers[0] : Hub Layers
        # layers[1] : Shroud Layers
        # layers[i][0] : List of layer volumes
        # layers[i][1] : List of bool values which tell if the layer is on a radius of zero
        #
        layers = layerRegion.getLayerList(configL["nSlices"])    
        
        #
        # The volume inside the flow channels is retrned as the mutliple bounded volume mv
        # its bounding surfaces are returned in the list bs
        #
        mv, bs = layerRegion.getUnstructuredRegion(configL["nSlices"])
        
        from dtOOPythonApp.builder import ( map3dTo3dGmsh_gridFromLayers ) 
        
        # 
        # Apply the mesh settings to the layers and the multiple bounded volume
        #
        self.container = map3dTo3dGmsh_gridFromLayers(
                mv = mv,
                bs = bs,
                label = "meshLayers",
                layers = layers,
                nElementsLayer = 15,
                firstElement = 0.001,
                elementSize_sw = 0.02,
                elementSize_circ = 0.01,
                charLengthMin = 0.02,
                charLengthMax = 0.04,
            ).buildExtract(self.container)
        #self.container = map3dTo3dGmsh_gridFromLayers(
        #        mv = mv,
        #        bs = bs,
        #        label = "meshLayers",
        #        layers = layers,
        #        nElementsLayer = 15,
        #        firstElement = 0.001,
        #        elementSize_sw = 0.08,
        #        elementSize_circ = 0.06,
        #        charLengthMin = 0.05,
        #        charLengthMax = 0.1,
        #    ).buildExtract(self.container)
       


    def createBlade(self, configB):
        
        """Create geometry of a bladed channel and its mesh topology.

        This method:

        - Creates the blade in the parameter space by combining the blade meanplane with the thickness distribution.
        - Creates six-sided mesh blocks surrounding the blade.
        - Creates six-sided mesh blocks at the blade’s trailing edge.
        - Creates FE-Meanplanes extending from the mesh blocks toward the
          inlet and outlet of the channel.
        - Maps the blade, the mesh blocks and the meanplanes onto a regular channel returned by the
          `radMeridionalContour` object.
        - Creates the grid channel as a multiple bounded volume defined by the FE-Meanplane and mesh block faces.
        - Applies mesh settings to the geometry regions.

        The inputs are provided via a configuration dictionary.
        The entries of type ``List[float]`` in this dictionary define the blade
        parameters along the blade span from hub to shroud.

        Parameters
        ----------
        configB : dict
          Dictionary containing the parameters for the layers with the
          following keys:

          - **label** (*str*): 
            Label.

          - **regChannel** (*int*): 
            Number of the regular channel in which the blade is created.

          - **nBlades** (*int*): 
            Number of total blades. Geometry will be 360°/nBlades.

          - **spanwiseCuts_mp** (*List[float]*): 
            Percentages of spanwise cuts where the blade's meanplane is created.

          - **alpha_1** (*List[float]*): 
            Blade inlet angles along spanwise direction from hub to shroud.

          - **alpha_2** (*List[float]*): 
            Blade outlet angles along spanwise direction from hub to shroud.

          - **ratioX** (*List[float]*): 
            Ratio between expanse of the blades' inlet and outlet angles for the x-direction along blade span.

          - **deltaY** (*List[float]*): 
            Blade length in y direction along blade span.

          - **offX** (*List[float]*): 
            Blade offsets in x-direction along blade span.

          - **offY** (*List[float]*): 
            Blade offsets in y-direction along blade span.

          - **spanwiseCuts_td** (*List[float]*): 
            Percentages of spanwise cuts where the blades' thickness distribution is created.

          - **t_le** (*List[float]*): 
            Thicknesses at the blades' leading edge along the blades' span.

          - **u_le** (*List[float]*): 
            Percentage of the u-positions of the leading edge thicknesses along the blades' span.

          - **t_mid** (*List[float]*): 
            Thicknesses at the blades' middle along the blades' span.

          - **u_mid** (*List[float]*): 
            Percentage of the u-positions of the thicknesses in the middle along the blades' span.

          - **t_te** (*List[float]*): 
            Thicknesses at the blades' trailing edge along the blades' span.

          - **u_te** (*List[float]*): 
            Percentage of the u-positions of the trailing edge thicknesses along the blades' span.

          - **adjustRadius** (*bool*): 
            Enables adjusting the blades curvature along the channel radius.

          - **orientation** (*int*): 
            Orientation of the blade in the regular channel.
            The values are:

                - 1 : Blade is oriented in u-direction of the regular channel.
                - -1: Blade is oriented in negative u-direction of the regular channel.
        
        Returns
        -------
        None
        """

        #
        # Assign the entries of the configuration dictionary to variables.
        #
        label = configB["label"]
        regChannel = configB["regChannel"]
        nBlades = configB["nBlades"]
        
        #
        # Two possible creation strategies based on configuration dictionary
        # 
        # 1. Curved meanplane and thickness mapped on regular channel
        #       - adjustRadius exists in dictionary
        #       - a conformal mapping between the blade geometries and the regular channel is performed
        #         (noMap = False)
        #
        # 2. Straight meanplane created in radially extending regular channel
        #       - meanplane and thichnes distribution are directly created in regular channel
        #         (noMap = True)
        #
        # dAdd_dir is used to set the correct directions of the blade and the mesh block surface
        #
        if "adjustRadius" in configB:
            adjustRadius = configB["adjustRadius"]
            noMap = False
            dAdd_dir = 1
        else:
            noMap = True
            dAdd_dir = -1


        spanwiseCuts_td = configB["spanwiseCuts_td"]
        t_le = configB["t_le"]
        u_le = configB["u_le"]
        t_mid = configB["t_mid"]
        u_mid = configB["u_mid"]
        t_te = configB["t_te"]
        u_te = configB["u_te"]
        
        orientation = configB["orientation"]
        
        tERounded = False
        
        for u in u_te:
            if u == 1.0:
                tERounded = True
                break
        
        #
        # Return the regular channel from the radMeridionalContour object,
        # which is created in the method createMeridional.
        #
        self.aG.push_back(
            self.radMeridionalContour.getRegChannel(
                regChannel, 1
            ) << "xyz_"+label+"_channel"
        )
        
        #
        # Create Blade Meanplane
        #
        if noMap == True:
            #
            # Create blade meanplane directly in regular channel
            #
            from dtOOPythonApp.builder import vec3dSurfaceTwoD_guideVaneMeanplane
            self.container = vec3dSurfaceTwoD_guideVaneMeanplane(
                label + "_meanplane",
                channel = self.aG["xyz_"+label+"_channel"],
                offRad = configB["offRad"],
                offAng = configB["offAng"],
                alpha = configB["alpha"],
                l_tot = configB["l_tot"],
                ratioL = configB["ratioL"]
            ).enableDebug().buildExtract( self.container )
        else:
            #
            # Create the blades' meanplane in the parameter space.
            #
            # The method fillInputList transforms the lists form the configuration
            # dictionary into a valid input for the class constructor
            # scaOneD_scaCurve2dOneDPointConstruct.
            #
            from dtOOPythonApp.builder import (
                analyticSurface_threePointMeanplaneFromRatio,
                scaOneD_scaCurve2dOneDPointConstruct
            )
            self.container = analyticSurface_threePointMeanplaneFromRatio(
              label + "_meanplane",
              configB["spanwiseCuts_mp"],
              alphaOne = scaOneD_scaCurve2dOneDPointConstruct(
                *self.fillInputList(configB["alpha_1"])
              )(),
              alphaTwo = scaOneD_scaCurve2dOneDPointConstruct(
                *self.fillInputList(configB["alpha_2"])
              )(),
              ratioX = scaOneD_scaCurve2dOneDPointConstruct(
                *self.fillInputList(configB["ratioX"])
              )(),
              deltaY = scaOneD_scaCurve2dOneDPointConstruct(
                *self.fillInputList(configB["deltaY"])
              )(),
              offX = scaOneD_scaCurve2dOneDPointConstruct(
                *self.fillInputList(configB["offX"])
              )(),
              offY = scaOneD_scaCurve2dOneDPointConstruct(
                *self.fillInputList(configB["offY"])
              )(),
            ).buildExtract( self.container )
        

        
        #
        # Create the blades' thickness distribution in the parameters space.
        #
        from dtOOPythonApp.builder import (
          vec3dSurfaceTwoD_fivePointsBSplineThicknessDistribution,
          scaOneD_scaCurve2dOneDPointConstruct
        )
        self.container = vec3dSurfaceTwoD_fivePointsBSplineThicknessDistribution(
          label + "_thicknessDistribution",
          spanwiseCuts_td,
          tLe = scaOneD_scaCurve2dOneDPointConstruct(
            *self.fillInputList(t_le)
          )(),
          uLe = scaOneD_scaCurve2dOneDPointConstruct(
            *self.fillInputList(u_le)
          )(),
          tMid = scaOneD_scaCurve2dOneDPointConstruct(
            *self.fillInputList(t_mid)
          )(),
          uMid = scaOneD_scaCurve2dOneDPointConstruct(
            *self.fillInputList(u_mid)
          )(),
          tTe = scaOneD_scaCurve2dOneDPointConstruct(
            *self.fillInputList(t_te)
          )(),
          uTe = scaOneD_scaCurve2dOneDPointConstruct(
            *self.fillInputList(u_te)
          )(),
          d = dAdd_dir
        ).buildExtract( self.container )

        #
        # Combine the meanplane and the thickness distribution in the parameter space.
        #
        dAdd = dtOO.discreteAddNormal()
        
        jsonObj = dtOO.jsonPrimitive(
            '{"option" : [{"name" : "debug", "value" : "false"}]}'
          )\
            .appendAnalyticFunction("_tt", self.aF[label + "_thicknessDistribution"])\
            .appendInt("_nU", 61)\
            .appendInt("_nV", 41)\
            .appendInt("_order", 3)\
            .appendDtVector3("_nf", dtOO.dtVector3(0,0,1))

        if tERounded == True:
            jsonObj.appendBool("_closeU", True)
            jsonObj.appendReal("_closeSmooth", 1.0)

        dAdd.jInit(
            jsonObj,
            None, None, self.aF, None
        )

        theAF = dAdd.applyAnalyticFunction(
          self.aF[label + "_meanplane"]
        )
        theAF.setLabel(label + "_blade")
        self.aF.push_back( theAF.clone() )
         
        #
        # Create a surface around the blade surface with a normal distance
        # specified by meshBlock_thickness.
        #
        #meshBlock_thickness = 0.035
        meshBlock_thickness = 0.025 
        fRef = dtOO.vec3dMuParserTwoD(
          str(dAdd_dir)+".0*"+str(meshBlock_thickness)+", xx, yy", "xx", "yy"
        )
        fRef.setLabel(label + "_thicknessMeshBlock")
        for i in range(2):
          fRef.setMin(i, +0.0)
          fRef.setMax(i, +1.0)
        self.aF.set( fRef.clone() )
        
        dAdd = dtOO.discreteAddNormal()
        
        jsonObj = dtOO.jsonPrimitive(
            '{"option" : [{"name" : "debug", "value" : "false"}]}'
          )\
            .appendAnalyticFunction("_tt", self.aF[label + "_thicknessMeshBlock"])\
            .appendInt("_nU", 61)\
            .appendInt("_nV", 41)\
            .appendInt("_order", 3)\
            .appendDtVector3("_nf", dtOO.dtVector3(0,0,1))
        if tERounded == True:
            jsonObj.appendBool("_closeU", True)
            jsonObj.appendReal("_closeSmooth", 1.0)

        dAdd.jInit(
            jsonObj,
            None, None, self.aF, None
        )
        #dAdd = dtOO.discreteAddNormal()
        #dAdd.jInit(
        #  dtOO.jsonPrimitive(
        #    '{"option" : [{"name" : "debug", "value" : "false"}]}'
        #    )\
        #    .appendAnalyticFunction("_tt", self.aF[label+"_thicknessMeshBlock"])\
        #    .appendInt("_nU", 61)\
        #    .appendInt("_nV", 41)\
        #    .appendInt("_order", 3)\
        #    .appendBool("_closeU", True)\
        #    .appendReal("_closeSmooth", 1.0)\
        #    .appendDtVector3("_nf", dtOO.dtVector3(0,0,1)),
        #  None, None, self.aF, None
        #)
        theAF = dAdd.applyAnalyticFunction( self.aF[label+"_blade"] )
        theAF.setLabel(label+"_meshBlock")
        self.aF.push_back( theAF.clone() )
        
        #
        # The class vec3dThreeD_skinAndSplit does the following tasks:
        #   - Create mesh blocks by splitting the mesh black surface.
        #   - Create trailing edge mesh blocks based on the first and last
        #     mesh block.
        #   - Creates a meanplane curve by offseting mesh block edges in the
        #     tangential directions of the mesh blocks.
        #     These curves will later be used to create peridoc faces of the
        #     grid channel.
        #     Two meanplane curves are created, one offset from the first mesh
        #     block extending towards the outlet and one offset from the meshblock
        #     specified with nMeanplaneBlocks extending towards the inlet of the
        #     regular channel.
        #

        
        # number of mesh block faces which will be part of the meanplane
        #  starts from 0
        nMeanplaneBlocks = 3
        
        if tERounded == True:
            
            # decrementing the number of meanplan blocks
            # because no trailing edge mesh blocks are created
            #nMeanplaneBlocks = nMeanplaneBlocks -1

            # split mesh block and create curves for meanplane
            from dtOOPythonApp.builder import vec3dThreeD_skinAndSplit
            self.container = vec3dThreeD_skinAndSplit(
              label =label+"_meshBlock",
              aFOne = self.aF[label+"_blade"],
              aFTwo = self.aF[label+"_meshBlock"],
              splitDim = 0,
              splits = [
                [0.00, 0.02],
                [0.02, 0.10],
                [0.10, 0.30],
                [0.30, 0.45],
                [0.45, 0.55],
                [0.55, 0.70],
                [0.70, 0.90],
                [0.90, 0.98],
                [0.98, 1.00],
              ],
            ).buildExtract(self.container) 
            

            from dtOOPythonApp.builder import vec3dCurveOneD_faceDirectionOffset
            
            self.container = vec3dCurveOneD_faceDirectionOffset(
              label =label+"_meshBlockCurve_out",
              surf = dtOO.vec3dSurfaceTwoD.DownCast(
                dtOO.vec3dTransVolThreeD.MustConstDownCast(
                  self.aF[label+"_meshBlock_0"]
                ).constPtrVec3dTwoD( 1 )
              ),
              thickness = 0.02,
              splitDim = 1,
              segPercent = 1,
            ).buildExtract(self.container) 
            
            self.container = vec3dCurveOneD_faceDirectionOffset(
              label =label+"_meshBlockCurve_in",
              surf = dtOO.vec3dSurfaceTwoD.DownCast(
                dtOO.vec3dTransVolThreeD.MustConstDownCast(
                  self.aF[label+"_meshBlock_3"]
                ).constPtrVec3dTwoD( 3 )
              ),
              thickness = 0.02,
              splitDim = 1,
              segPercent = 1,
            ).buildExtract(self.container) 
        
        else:
            # split mesh block and create curves for meanplane
            from dtOOPythonApp.builder import vec3dThreeD_skinAndSplit
            self.container = vec3dThreeD_skinAndSplit(
              label =label+"_meshBlock",
              aFOne = self.aF[label+"_blade"],
              aFTwo = self.aF[label+"_meshBlock"],
              splitDim = 0,
              splits = [
                [0.00, 0.10],
                [0.10, 0.30],
                [0.30, 0.45],
                [0.45, 0.55],
                [0.55, 0.70],
                [0.70, 0.90],
                [0.90, 1.00],
              ],
              tEMeshBlockThickness = meshBlock_thickness,
              meanplaneFromBlocks = True,
              meanplaneExtOut = 0.02,
              meanplaneExtIn = 0.03,
              nMeanplaneBlocks = nMeanplaneBlocks
            ).buildExtract(self.container) 
        #
        # Build the two meanplane faces extending from the mesh block edges 
        # to the tangentially offset meanplane curves.
        #
        for i in range(2):
            #
            # curve seqence is switched with c0 and c1 between inlet and outlet in 
            # order to keep u and v directions consistent with the mesh block faces.
            #
            if i == 0:
                at = "in"
                c0 = 0
                c1 = 1
            elif i == 1:
                at = "out"
                c0 = 1
                c1 = 0
            # 
            # Create the fe_meanplane faces. Those will later be used as part of the
            # periodic faces of the grid channel.
            #
            surf = dtOO.vec3dSurfaceTwoD(
                dtOO.bSplineSurface_exchangeSurfaceConstructOCC(
                    dtOO.bSplineSurface_skinConstructOCC(
                        dtOO.vec3dCurveOneD.MustDownCast(
                            self.aF[label+"_meshBlockCurve_"+at+str(c0)]
                        ).ptrConstDtCurve(),
                        dtOO.vec3dCurveOneD.MustDownCast(
                            self.aF[label+"_meshBlockCurve_"+at+str(c1)]
                        ).ptrConstDtCurve()
                    ).result()
                ).result()
            )
            self.aF.push_back(surf << label+"_fe_meanplane_"+at+str(0))
         
        #
        # Transform the analyticFunction objects of the 
        # geometries in analyticGeometry objects
        #
        if noMap == True:
            #
            # Direct transformation when the objects were already created in the regular channel
            #
            for ii in [label+"_meanplane", label+"_blade", label+"_meshBlock",]:
                
                theAG = dtOO.analyticSurface(
                        dtOO.vec3dSurfaceTwoD.MustDownCast(
                            self.aF[ii]
                        ).constPtrDtSurface()
                    ).clone()

                theAG.setLabel("xyz_"+ii)
                self.aG.push_back( theAG.clone() )
            
            for iNum in self.aF.getIndices(label+"_fe_meanplane_*"):
                ii = self.aF.getLabel( iNum )
                theAG = dtOO.analyticSurface(
                        dtOO.vec3dSurfaceTwoD.MustDownCast(
                            self.aF[ii]
                        ).constPtrDtSurface()
                    ).clone()

                theAG.setLabel("xyz_"+ii)
                self.aG.push_back( theAG.clone() )

            for iNum in self.aF.getIndices(label+"_meshBlock_*"):
                ii = self.aF.getLabel( iNum )
                theAG = dtOO.vec3dThreeDInMap3dTo3d(
                    dtOO.vec3dThreeD.MustDownCast(
                        self.aF[ii]
                    ), 
                    dtOO.infinityMap3dTo3d()
                )
                theAG.setLabel("xyz_"+ii)
                self.aG.push_back( theAG.clone() )
                
            for iNum in self.aF.getIndices(label+"_meshBlockCurve_*"):
                ii = self.aF.getLabel( iNum )
                theAG = dtOO.analyticCurve(
                        dtOO.vec3dCurveOneD.MustDownCast(
                            self.aF[ii]
                        ).ptrConstDtCurve()
                    ).clone()
                theAG.setLabel("xyz_"+ii)
                self.aG.push_back( theAG.clone() )

        else:
            #
            # Transformation through conformal mapping with regular channel
            # 
            # Create a conformal mapping object with the regular channel
            # and the adjustRadius setting.
            #
            conMap = dtOO.uVw_phirMs()
            conMap.jInit(
              dtOO.jsonPrimitive()\
                .appendStr("label", "uVw_phirMs")\
                .appendInt("_nV", 31)\
                .appendInt("_nW", 11)\
                .appendBool("_adjustRadius", adjustRadius)\
                .appendAnalyticGeometry(\
                  "_rM2d", \
                  self.aG.get("xyz_" + label + "_channel")\
                ),\
              None, None, None, self.aG \
            )
            self.bC.dtTransformer().add( conMap.clone() )
          
            #
            # Apply the conformal mapping object the following geometries.
            #
            #   - faces of the blade meanplane, the blade and the mesh blocks
            #
            for ii in [label+"_meanplane", label+"_blade", label+"_meshBlock",]:
              theAG = dtOO.vec3dTwoDInMap3dTo3d(
                dtOO.vec3dTwoD.MustConstDownCast(
                  conMap.applyAnalyticFunction(self.aF[ii].clone())
                ),
                dtOO.map3dTo3d.ConstDownCast( self.aG["xyz_"+label+"_channel"] )
              )
              theAG.setLabel("xyz_"+ii)
              self.aG.push_back( theAG.clone() )
            #
            #   - fe_meanplane faces extending tangentially from the mesh blocks.
            #
            for iNum in self.aF.getIndices(label+"_fe_meanplane_*"):
              ii = self.aF.getLabel( iNum )
              theAG = dtOO.vec3dTwoDInMap3dTo3d(
                dtOO.vec3dTwoD.MustConstDownCast(
                  conMap.applyAnalyticFunction(self.aF[ii].clone())
                ),
                dtOO.map3dTo3d.ConstDownCast( self.aG["xyz_"+label+"_channel"] )
              )
              theAG.setLabel("xyz_"+ii)
              self.aG.push_back( theAG.clone() )
            #
            #   - mesh block volumes
            #
            for iNum in self.aF.getIndices(label+"_meshBlock_*"):
              ii = self.aF.getLabel( iNum )
              theAG = dtOO.vec3dThreeDInMap3dTo3d(
                dtOO.vec3dThreeD.MustConstDownCast(
                  conMap.applyAnalyticFunction(self.aF[ii].clone())
                ),
                dtOO.map3dTo3d.ConstDownCast( self.aG["xyz_"+label+"_channel"] )
              )
              theAG.setLabel("xyz_"+ii)
              self.aG.push_back( theAG.clone() )
            #
            #   - mesh block curves which were used to create the fe_meanplane faces
            #
            for iNum in self.aF.getIndices(label+"_meshBlockCurve_*"):
              ii = self.aF.getLabel( iNum )
              theAG = dtOO.vec3dOneDInMap3dTo3d(
                dtOO.vec3dOneD.MustConstDownCast(
                  conMap.applyAnalyticFunction(self.aF[ii].clone())
                ),
                dtOO.map3dTo3d.ConstDownCast( self.aG["xyz_"+label+"_channel"] )
              )
              theAG.setLabel("xyz_"+ii)
              self.aG.push_back( theAG.clone() )
        
        #
        # Collect the curves for the fe_meanplane faces.
        # The curves extend form hub to shroud and are tangentially 
        # offset from the specified mesh block faces
        #
        meshBlockCurves = dtOO.labeledVectorHandlingAnalyticGeometry()
        for iNum in self.aG.getIndices("xyz_"+label+"_meshBlockCurve_*"):
            ii = self.aG.getLabel( iNum )
            meshBlockCurves.push_back(self.aG[ii].clone())
        
        #
        # Create the fe_meanplane surfaces extending from the tangentially 
        # offset meshblock curves to the inlet or the outlet.
        #
        from dtOOPythonApp.builder import analyticSurface_inOutFeMeanplane
        self.container = analyticSurface_inOutFeMeanplane(
            prefix = "xyz",
            label = label,
            channel = self.aG["xyz_"+label+"_channel"],
            curves = meshBlockCurves
        ).enableDebug().buildExtract(self.container)
         
        #
        # Order the gemetries for the creation of the grid channel.
        #
        # Collect and organize the mesh block volumes.
        # The mesh blocks are ordered by their number.
        #
        blocks = []
        for iNum in self.aG.getIndices("xyz_"+label+"_meshBlock_*"):
            blocks.append( self.aG[ self.aG.getLabel( iNum ) ] )
        blocks.sort(key=lambda x: int(x.getLabel().split('_')[-1]))
        
        #
        # Collect the coupling and meanplane faces.
        # The list couplingFaces contains the faces which will connect the
        # mesh block to the grid channel.
        # The list meanplaneFaces contains the faces which will form the 
        # periodic boundaries of the grid.
        #
        couplingFaces = []
        meanplaneFaces = []
        
        #
        # Faces extending from outlet to the mesh block trailing edge. 
        #
        meanplaneFaces.append(dtOO.map2dTo3d.MustDownCast(self.aG["xyz_"+label+"_fe_meanplane_out1"]))
        meanplaneFaces.append(dtOO.map2dTo3d.MustDownCast(self.aG["xyz_"+label+"_fe_meanplane_out0"]))
        
        #
        # Iterate over the mesh blocks and sort the faces.
        #
        for i, block in enumerate(blocks):
          face = dtOO.map3dTo3d.MustDownCast( block ).segmentConstWPercent( 1.0 )
          
          #
          # Append the specified meanplane and coupling to the lists. 
          #
          if i <= nMeanplaneBlocks:
            meanplaneFaces.append(face)
            self.aG.push_back(face.clone() << "xyz_"+label+"_meanplaneFaceOnBlock_"+str(i))
          else:
            couplingFaces.append(face)
        
        #
        # Faces extending from the mesh block leading edge area to the inlet.
        #
        meanplaneFaces.append(dtOO.map2dTo3d.MustDownCast(self.aG["xyz_"+label+"_fe_meanplane_in0"]))
        meanplaneFaces.append(dtOO.map2dTo3d.MustDownCast(self.aG["xyz_"+label+"_fe_meanplane_in1"]))
        
        if tERounded == False:
            #
            # Last two coupling faces at the trailing edge.
            #
            couplingFaces.append(dtOO.map3dTo3d.MustDownCast(blocks[-1]).segmentConstUPercent( 1.0 ))
            couplingFaces.append(dtOO.map3dTo3d.MustDownCast(blocks[0]).segmentConstUPercent( 0.0 ))
        
        #
        # Create the grid channel.
        #
        from dtOOPythonApp.builder import multipleBoundedVolume_gridChannel
        gridChannel = multipleBoundedVolume_gridChannel(
            label = label,
            channel = self.aG["xyz_"+label+"_channel"],
            meanplanes = meanplaneFaces,
            couplings = couplingFaces,
            nBlades = nBlades,
            orientation = orientation,
            tERounded = tERounded
        ).enableDebug() 
        self.container = gridChannel.buildExtract(self.container)
        
        #
        # Return the multiple bounded volume of the grid channel as well
        # as the list with its boundary faces.
        #
        gc, gcFaces = gridChannel.getGridChannel()
        self.aG.push_back(
            gc << "xyz_"+label+"_gridChannel"
        )
                  
        #
        # Apply the mesh settings to the grid channel.
        #
        from dtOOPythonApp.builder import (
          map3dTo3dGmsh_gridFromMultipleBoundedVolumeAndBlocks
        )
        # Mesh topology settings for round trailing edge
        self.container = map3dTo3dGmsh_gridFromMultipleBoundedVolumeAndBlocks(
            label = label+"_mesh",
            channel = self.aG["xyz_"+label+"_gridChannel"],
            channelFaces = gcFaces,
            blocks = blocks,
            nMeanplaneBlocks = nMeanplaneBlocks,
            blade = self.aG["xyz_"+label+"_blade"],
            nBoundaryLayers = 15,
            nElementsSpanwise = 50,
            nElementsNormal = 6,
            firstElementSizeHubToShroud = 0.001,
            firstElementSizeNormalBlade = 0.001,
            bladeHubElementSize = scaOneD_scaCurve2dOneDPointConstruct(
                [
                   dtOO.dtPoint2(0.00, 0.002),
                   dtOO.dtPoint2(0.01, 0.003),
                   dtOO.dtPoint2(0.05, 0.014),
                   dtOO.dtPoint2(0.10, 0.015),
                   dtOO.dtPoint2(0.45, 0.003),
                   dtOO.dtPoint2(0.50, 0.002),
                   dtOO.dtPoint2(0.55, 0.003),
                   dtOO.dtPoint2(0.90, 0.015),
                   dtOO.dtPoint2(0.95, 0.014),
                   dtOO.dtPoint2(0.99, 0.003),
                   dtOO.dtPoint2(1.00, 0.002),
                ], 1
            )(),
            bladeHubElementScale = 0.3,
            charLengthMax=0.03,
            charLengthMin=0.015,
            meshTEBlocks = not(tERounded),
        ).enableDebug().buildExtract( self.container )
         
        # Mesh topology setting for sharp trailing edge
        #self.container = map3dTo3dGmsh_gridFromMultipleBoundedVolumeAndBlocks(
        #    label = label+"_mesh",
        #    channel = self.aG["xyz_"+label+"_gridChannel"],
        #    channelFaces = gcFaces,
        #    blocks = blocks,
        #    nMeanplaneBlocks = nMeanplaneBlocks,
        #    blade = self.aG["xyz_"+label+"_blade"],
        #    nBoundaryLayers = 15,
        #    nElementsSpanwise = 30,
        #    nElementsNormal = 7,
        #    firstElementSizeHubToShroud = 0.001,
        #    firstElementSizeNormalBlade = 0.001,
        #    bladeHubElementSize = scaOneD_scaCurve2dOneDPointConstruct(
        #        [
        #           dtOO.dtPoint2(0.00, 0.04),
        #           dtOO.dtPoint2(0.45, 0.007),
        #           dtOO.dtPoint2(0.50, 0.007),
        #           dtOO.dtPoint2(0.55, 0.007),
        #           dtOO.dtPoint2(1.00, 0.04),
        #        ], 1
        #    )(),
        #    bladeHubElementScale = 0.3,
        #    charLengthMax=0.2,
        #    charLengthMin=0.1,
        #    meshTEBlocks = True,
        #).enableDebug().buildExtract( self.container )

    def fillInputList(self, inList): 
        """Create inputs for scaOneD_scaCurve2dOneDPointConstruct class.

        Takes the input lists for the :meth:`createBlade` method and transforms them
        into inputs of the scaOneD_scaCurve2dOneDPointConstruct class.     

        Parameters
        ----------
        inList : List[float]
          List containing the input values along the blades' span.

        Returns
        -------
        outList : List[dtPoint2[float, float]]
          Input parameter and its percenatage along the blades' span.
          
        order : int
          Order of the function.

        """
        #
        # If the input list has only one entrie the values are kept 
        # constant along the spanwise direction.
        #
        if len(inList) == 1:
            #
            # The inputs will be the same at spanwiseCut 0 and 1.
            # The odere is one.
            #
            outList = [
                        dtOO.dtPoint2(0.00, inList[0]), 
                        dtOO.dtPoint2(1.00, inList[0]),
                      ]      
            order = 1
        
        #
        # Else the parameter vary along the spanwise direction.
        #
        else:
            outList = []
            #
            # Iterate over the input list.
            #
            for nL in range(len(inList)):
                #
                # Calculate the percentage of the spanwise cut from the normalized index
                #
                cutPercent = nL/(len(inList)-1)
                #
                # Append the percentage and input as a dtPoint2 object to the outList.
                #
                outList.append(dtOO.dtPoint2(cutPercent, inList[nL]),)
            
            #
            # The order is one less than the length of the input list.
            #
            order = len(inList) -1
        
        return outList, order
         

    def createOFCase(self, h_inlet, nCores = 1):
    
 
        dtOO.lVHOstateHandler().makeState(self.state_)

        #
        # draft tube
        #
        
        
        #LEGACY_DIR = Path(__file__).resolve().parent
        #SAUGROHR = LEGACY_DIR / "saugrohr.cgns"

        #rmsh = dtOO.readMOABMesh()
        #rmsh.jInit(
        #    dtOO.jsonPrimitive(
        #        '{"label" : "dt_mesh", "_fileName" : "'+str(SAUGROHR)+'"}'
        #    ), 
        #    None, None, None, None, None
        #)
        rmsh = dtOO.readMOABMesh()
        rmsh.jInit(
            dtOO.jsonPrimitive(
                '{"label" : "dt_mesh", "_fileName" : "./radmeridional_files/saugrohr.cgns"}'
            ), 
            None, None, None, None, None
        )
        rmsh.makeGrid()
        
        self.bV.push_back( rmsh )

        ob = dtOO.bVOFaceToPatchRule()
        ob.thisown = False
        ob.jInit(
          dtOO.jsonPrimitive(
            '{'
              '"_patchRule" : ['
                '":meshSet_2d_0::dt_mesh_wall:",'
                '":meshSet_2d_1::dt_mesh_central:",'
                '":meshSet_2d_2::dt_mesh_vent:",'
                '":meshSet_2d_3::dt_mesh_outlet:",'
                '":meshSet_2d_4::dt_mesh_inlet:"'
              '],'
              '"_regRule" : ['
                '":meshSet_3d_0::dt_mesh:"'
              ']'
            '}'
          ),
          rmsh
        )
        ob.postUpdate()
        
        ob = dtOO.bVOOrientCellVolumes()
        ob.thisown = False
        ob.jInit(
            dtOO.jsonPrimitive('{"_positive" : true}'), rmsh
        )
        ob.postUpdate()

        #ob = dtOO.bVOWriteMSH()
        #ob.thisown = False
        #ob.jInit(
        #        dtOO.jsonPrimitive('{"_filename" : "dt_mesh.msh", "_saveAll" : true}'),
        #  None, None, None, None, None, rmsh
        #)
        #ob.postUpdate()
        
        logging.info("DEBUG 1")
         
        from dtOOPythonApp.builder import (
          ofOpenFOAMCase_turboMachine,
          ofOpenFOAMCase_setupWrapper
        )

        self.container = ofOpenFOAMCase_turboMachine(
          label = "of",
          bVs = [
            self.bV["gv_mesh"], 
            self.bV["ru_mesh"], 
            self.bV["dt_mesh"],
          ],
          dictRule = \
              ofOpenFOAMCase_setupWrapper.controlDict(
                application = "simpleFoam",
                endTime = 2000,
                # Patches where Q and PT is tracked
                QPatches = ['gv_mesh_inlet', 'gv_mesh_outlet', 
                            'ru_mesh_inlet', 'ru_mesh_outlet',
                            'dt_mesh_inlet', 'dt_mesh_outlet',
                            'gv_mesh_suction', 'gv_mesh_pressure',
                            'ru_mesh_suction', 'ru_mesh_pressure'],
                PTPatches = ['gv_mesh_inlet', 'gv_mesh_outlet',
                             'ru_mesh_inlet', 'ru_mesh_outlet',
                             'dt_mesh_inlet', 'dt_mesh_outlet',
                             'gv_mesh_suction', 'gv_mesh_pressure',
                             'ru_mesh_suction', 'ru_mesh_pressure'],
                FPatches = ['gv_mesh_blade', 'ru_mesh_blade'],
                libs = [
                  "libsimpleFunctionObjects.so",
                  ##"libsimpleSwakFunctionObjects.so",
                  ##"libmappedFieldFixedValue.so",
                  "libmixingPlane.so",
                ]
              )
            + ofOpenFOAMCase_setupWrapper.decomposeParDict(nCores, 'metis')
            + ofOpenFOAMCase_setupWrapper.fvSchemes()
            + ofOpenFOAMCase_setupWrapper.fvSolution()
            + ofOpenFOAMCase_setupWrapper.transportModel()
            + ofOpenFOAMCase_setupWrapper.turbulenceProperties()
            + ofOpenFOAMCase_setupWrapper.MRFProperties(
                cellZones = ["ru_mesh",],
                omegas    = [375*2*np.pi/60,],
                nonRotatingPatches = [
                  [
                    "ru_mesh_suction", "ru_mesh_pressure",
                    "ru_mesh_inlet", "ru_mesh_outlet",
                  ],
                ],
                patches = [],
                axes = [dtOO.dtVector3(0,0,-1)],
                origins = [dtOO.dtPoint3(0,0,0)]
              ),
            fieldRules = [
              ofOpenFOAMCase_setupWrapper.fieldRuleString("U", [0.0,0.0,-1.0,]),
              ofOpenFOAMCase_setupWrapper.fieldRuleString("p", [0.0,]),
              ofOpenFOAMCase_setupWrapper.fieldRuleString("k", [0.1,]),
              ofOpenFOAMCase_setupWrapper.fieldRuleString("omega", [0.1,]),
              ofOpenFOAMCase_setupWrapper.fieldRuleString("nut", [0.1,]),
            ],
            setupRules = [
              ofOpenFOAMCase_setupWrapper.emptyRuleString(),
              ## meshInlet
              ofOpenFOAMCase_setupWrapper.cylindricalInletRuleString(
                "gv_mesh_inlet",
                ["U"],
                [ [-2.92*2.7,-7.23*2.7,0], ]
              ),
              ofOpenFOAMCase_setupWrapper.inletRuleString(
                "gv_mesh_inlet",
                ["p", "k", "omega",],
                [ [0], [0.1, 0.10], [0.032*h_inlet, 0.1] ]
              ),
              ofOpenFOAMCase_setupWrapper.wallRuleString(
                "gv_mesh_shroud",
                ["omega", "U", "p", "k", "nut"]
              ),
               ofOpenFOAMCase_setupWrapper.wallRuleString(
                "gv_mesh_hub",
                ["omega", "U", "p", "k", "nut"]
              ),
              ofOpenFOAMCase_setupWrapper.wallRuleString(
                "gv_mesh_blade",
                ["omega", "U", "p", "k", "nut"]
              ),
              ofOpenFOAMCase_setupWrapper.cyclicAmiRuleString(
                "gv_mesh_suction", "gv_mesh_pressure"
              ),
              # mixing plane?
              #ofOpenFOAMCase_setupWrapper.cyclicAmiRuleString(
              #  "meshInlet_outlet", "meshChannel_inlet",
              #  rotAxis = None,
              #  rotCentre = None
              #),
              ofOpenFOAMCase_setupWrapper.mixingPlaneRuleString(
                "gv_mesh_outlet", "ru_mesh_inlet",
                ["U", "p", "k", "omega",],
                axis = dtOO.dtVector3(0,0,1),
                origin = dtOO.dtPoint3(0,0,0),
                stackAxis = "Z",
                discretization = "userDefined",
                planes = 40,
                planesBl = 15,
                gradingIf = "false"
              ),

              # runner
              ofOpenFOAMCase_setupWrapper.wallRuleString(
                "ru_mesh_hub",
                ["omega", "U", "p", "k", "nut"]
              ),
              ofOpenFOAMCase_setupWrapper.wallRuleString(
                "ru_mesh_shroud",
                ["omega", "U", "p", "k", "nut"]
              ),
              ofOpenFOAMCase_setupWrapper.wallRuleString(
                "ru_mesh_blade",
                ["omega", "U", "p", "k", "nut"]
              ),
              ofOpenFOAMCase_setupWrapper.cyclicAmiRuleString(
                "ru_mesh_suction", "ru_mesh_pressure"
              ),
              ofOpenFOAMCase_setupWrapper.mixingPlaneRuleString(
                "ru_mesh_outlet", "dt_mesh_inlet",
                ["U", "p", "k", "omega",],
                axis = dtOO.dtVector3(0,0,1),
                origin = dtOO.dtPoint3(0,0,0),
                stackAxis = "R",
                discretization = "userDefined",
                planes = 40,
                planesBl = 15,
                gradingIf = "false"
              ),
              
              # draft tube
              ofOpenFOAMCase_setupWrapper.wallRuleString(
                "dt_mesh_vent",
                ["omega", "U", "p", "k", "nut"]
              ),
              ofOpenFOAMCase_setupWrapper.wallRuleString(
                "dt_mesh_central",
                ["omega", "U", "p", "k", "nut"]
              ),
              ofOpenFOAMCase_setupWrapper.wallRuleString(
                "dt_mesh_wall",
                ["omega", "U", "p", "k", "nut"]
              ),
              ofOpenFOAMCase_setupWrapper.outletRuleString(
                "dt_mesh_outlet",  
                ["U", "p", "k", "omega",]
              ),
              #ofOpenFOAMCase_setupWrapper.outletRuleString(
              #  "gv_mesh_outlet",  
              #  ["U", "p", "k", "omega",]
              #),
            ]
        ).buildExtract( self.container )
        

        logging.info("DEBUG 2")
        #
        # Output to log of the current state label
        #
        logging.info( 
          "Current state is > %s <." % (dtOO.lVHOstateHandler().commonState()) 
        )
        
        #self.cDir_ = dC["of"].getDirectory(dtOO.lVHOstateHandler().commonState())
        self.dC["of"].runCurrentState()
    
    def setupSim(self):
        """Setup the simulation.

        Perform the simulation using foamlib. The simulation runs for 500 
        iterations as a laminar simulation. Afterwards, it is switched to turbulent
        mode.
        """
        try:
            #
            # Create an FoamCase object of foamlib to control the simulation; the
            # "getDirectory" function returns the case directory that was created
            #
            fc = foamlib.FoamCase(self.cDir_)

            fc.turbulence_properties["RAS"]["turbulence"] = False
            fc.fv_schemes['gradSchemes']['none'] = ('cellLimited', 'Gauss', 'linear', 0.33)
            fc.fv_schemes['gradSchemes']['grad(p)'] = ('cellLimited', 'Gauss', 'linear', 0.33)
            fc.fv_schemes['gradSchemes']['grad(U)'] = ('cellLimited', 'Gauss', 'linear', 0.33)
            fc.fv_schemes['divSchemes']['div(phi,U)'] = \
                ('Gauss', 'linearUpwind', 'cellLimited', 'Gauss', 'linear', 0.33)
            fc.fv_schemes["mixingInterface"] = {
                "U": "consistentAveraging",
                "p": "consistentAveraging",
                "k": "fluxAveraging",
                "epsilon": "fluxAveraging",
                "omega": "fluxAveraging"
              }
            fc.fv_solution["relaxationFactors"] = {
                "p": 0.2,
                "U": 0.4,
                "k": 0.6,
                "epsilon": 0.6,
                "omega": 0.6
              }
            fc.fv_solution["SIMPLE"] = {
                "nNonOrthogonalCorrectors": 20,
                "residualControl": {
                    "p": 1e-5,
                    "U": 1e-5,
                    "k": 1e-5,
                    "omega": 1e-5,
                },
                #"consistent": "yes"
              }

            fc.control_dict['DebugSwitches'] = {
                  'mixingInterfacePolyPatch': 2
                }
            fc.control_dict['writeInterval'] = 100
            fc.control_dict['endTime'] = 100
            #solver_cmd = [*self.solver_launcher_, "simpleFoam"]
            #if cpus_per_task > 1:
            #    solver_cmd.append("-parallel")
            #fc.run(cmd=solver_cmd)
            ##if cpus_per_task > 1:
            ##    fc.run(cmd=["mpiexec", "--oversubscribe", "-n", f"{cpus_per_task}","simpleFoam", "-parallel"])
            ##else:
            ##    fc.run()

            #fc.control_dict['endTime'] = 2000
            #fc.control_dict['writeInterval'] = 100
            ##fc.control_dict['purgeWrite'] = 10
            #fc.turbulence_properties["RAS"]["turbulence"] = True
            #fc.run(cmd=solver_cmd)

            ##if cpus_per_task > 1:
            ##    fc.run(cmd=["mpiexec", "--oversubscribe", "-n", f"{cpus_per_task}","simpleFoam", "-parallel"])
            ##else:
            ##    fc.run()

            #if cpus_per_task > 1:
            #    fc.run(["reconstructPar", '-time', '500,2000'])
            #    #fc.run(["reconstructPar", '-time', '100'])

        except:
            logging.exception(f"Failed: {self.state_}.")

    
    @staticmethod
    def failedFitness():
        """Failed fitness.

        Returns the value that represents a failed design.

        Returns
        -------
        float
          Fitness for a failed design.
        """
        return runRadMeridional.sys.float_info.max    

    def evaluate(self, end_time):

        _omega = np.abs(
          foamlib.FoamFile(self.cDir_+'/constant/MRFProperties')['MRF_ru_mesh']['omega']
        )
        fc = foamlib.FoamCase(self.cDir_)
        
        _rho = 997.
        _g = 9.81
        for var in ["U", "p",]:
          for patch in [
                  #"gv_mesh_inlet", "gv_mesh_outlet", 
                  "ru_mesh_inlet", "ru_mesh_outlet", 
                  #"dt_mesh_inlet", "dt_mesh_outlet"
                ]:
            fc.run(["patchToCsv", var, patch])
        
        _time = str(end_time) 
        #_time = "2000"

        #pT_gv_in = dtScalarDeveloping( 
        #    dtDeveloping(self.cDir_+"/postProcessing/PT_gv_mesh_inlet").Read(pattern={"*.dat": ":,1:"}) 
        #)
        #pT_gv_out = dtScalarDeveloping( 
        #    dtDeveloping(self.cDir_+"/postProcessing/PT_gv_mesh_outlet").Read(pattern={"*.dat": ":,1:"}) 
        #)
        pT_ru_in = dtScalarDeveloping( 
            dtDeveloping(self.cDir_+"/postProcessing/PT_ru_mesh_inlet").Read(pattern={"*.dat": ":,1:"}) 
        )
        pT_ru_out = dtScalarDeveloping(
            dtDeveloping(self.cDir_+"/postProcessing/PT_ru_mesh_outlet").Read(pattern={"*.dat": ":,1:"}) 
        )
        #pT_dt_in = dtScalarDeveloping(
        #    dtDeveloping(self.cDir_+"/postProcessing/PT_dt_mesh_inlet").Read(pattern={"*.dat": ":,1:"}) 
        #)
        #pT_dt_out = dtScalarDeveloping(
        #    dtDeveloping(self.cDir_+"/postProcessing/PT_dt_mesh_outlet").Read(pattern={"*.dat": ":,1:"}) 
        #)

        Q_ru_out = dtScalarDeveloping( 
            dtDeveloping(self.cDir_+"/postProcessing/Q_ru_mesh_outlet").Read(pattern={"*.dat": ":,1:"}) 
        )
        Q_ru = np.abs(Q_ru_out.MeanLast(100))
        changeLastQ_ru = np.abs(Q_ru_out.ChangeLast(100))

        
        #dh_gv0 = (pT_gv_out.MeanLast(100) - pT_gv_in.MeanLast(100))/_g
        self.dh_ru_ = (pT_ru_out.MeanLast(100) - pT_ru_in.MeanLast(100))/_g
        changeLastDh_ru = (pT_ru_out.ChangeLast(100) - pT_ru_in.ChangeLast(100))/_g
        #dh_dt0 = (pT_dt_out.MeanLast(100) - pT_dt_in.MeanLast(100))/_g

        #dh = dh_gv0 + dh_ru0 + dh_dt0
        #logging.info("dh = %f" % dh)
        
        F = dtForceDeveloping( 
            dtDeveloping(
                #self.cDir_+"/postProcessing/F_ru_mesh_blade"
                self.cDir_+"/postProcessing/F_ru_mesh_blade"
            ).Read(pattern={'force.dat' : ':,4:10', 'moment.dat' : ':,4:10', '*.*' : ''}) 
        )

        #pt_globIn = pT_gv_in.MeanLast(10)
        #pt_globOut = pT_dt_out.MeanLast(10)
        #F_z = F.MomentMeanLast(10)[2]

        self.M_z_ = F.MomentMeanLast(100)[2]
        changeLastM_z = F.MomentChangeLast(100)[2]

        self.eta_ = self.M_z_ * _omega / (_rho*_g*self.dh_ru_*Q_ru)
        
        logging.info("Objective Values of State %s:" % self.state_)
        logging.info("Q_ru = %f" % Q_ru)
        logging.info("Change Last 100 Q_ru = %f" % changeLastQ_ru)
        logging.info("dh_ru = %f" % self.dh_ru_)
        logging.info("Change Last 100 dh_ru = %f" % changeLastDh_ru)
        logging.info("M_z = %f" % self.M_z_)
        logging.info("Change Last 100 M_z = %f" % changeLastM_z)

        logging.info("eta = %f" % self.eta_)

        #
        # Check if the simulated geometry is a pump or a turbine; if it is a pump,
        # return an artificial value that is greater than all other fitness values
        #
        #failed_fit = min(10,max(10. * np.abs(fit),30))
        
        self.objectiveOk_ = True
        self.convergenceOk_ = True
        
        Q_ru_max = 27.5/15 * 2

        if (dh_ru_ > 0.0) or (M_z_ > 0.0 ) or (eta_ > 1.0) or (Q_ru > Q_ru_max):
            logging.info("Objective Values Unphysical")
            self.objectiveOk_ = False
        
        thr = 0.01  # threshold
        if (
            np.abs(changeLastQ_ru) > thr * np.abs(Q_ru)
            or np.abs(changeLastDh_ru) > thr * np.abs(self.dh_ru_)
            or np.abs(changeLastM_z) > thr * np.abs(self.M_z_)
        ):
            logging.info("Convergence Criteria not Reached")
            self.convergenceOk_ = False
            #fit = failed_fit

    def GiveFitness(self):
        

        if self.objectiveOk_ and self.convergenceOk_:
            
            # desired runner head in optimal operation point
            dh_ru_opt = 200

            #fit = np.abs(dh_ru + 0.8)/0.8 + (1.0 - eta)
            #fit = -1*(np.abs(self.dh_ru_)*self.eta_)
            fit = (1 - self.eta_)*(np.abs(np.abs(self.dh_ru_) - dh_ru_opt))/dh_ru_opt

        else:
            fit = 0.0
            if not self.objectiveOk_:
                fit = fit + 3.0
            if not self.convergenceOk_:
                fit = fit + 2.0


        fitness_extra = {
            "dh_ru": self.dh_ru_,
            "M_z": self.M_z_,
            "eta": self.eta_,
        }

        #
        # Return fitness value
        #
        return fit, fitness_extra

    def delete_case(self):
      label = "of_"
      #dir_path = self.cDir_
      dir_path = "./of_"+self.state_
      try: 
          #shutil.rmtree(dir_path)

          for file in [
            #self.wd_ +"/"+ self.state_ + "_gv_mesh_debug.msh",
            #self.wd_ +"/"+ self.state_ + "_gv_mesh.msh",
            #self.wd_ +"/"+ self.state_ + "_ru_mesh_debug.msh",
            #self.wd_ +"/"+ self.state_ + "_ru_mesh.msh",
            "./"+ self.state_ + "_gv_mesh_debug.msh",
            "./"+ self.state_ + "_gv_mesh.msh",
            "./"+ self.state_ + "_ru_mesh_debug.msh",
            "./"+ self.state_ + "_ru_mesh.msh",
                ]:
            os.remove(file)

          logging.debug(f"Deleted OpenFoam Case of state {self.state_} successfully.")
      except Exception as e:
          logging.warning(f"Failed deleting OpenFoam Case of state {self.state_}.")
          logging.warning(e)

    def getContainer(self):
        """Return the container object.
        
        Is used to return the container objects.

        Parameters
        ----------
        None

        Returns
        -------
        container: dtBundle
          Initialization of the dtBundle.
        """
        return self.container
