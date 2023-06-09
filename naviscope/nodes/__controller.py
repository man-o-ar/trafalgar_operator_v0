#!/usr/bin/env python3
########################################################################
# Filename    : __controller.py
# Description : propulsion node 
# Author      : Man'O'AR
# modification: 17/01/2023
########################################################################
import sys
import json
import math
import numpy as np
import socket

import rclpy
from rclpy.node import Node

from std_msgs.msg import String, Int8, UInt16
from geometry_msgs.msg import Vector3

from rclpy.qos import qos_profile_sensor_data

from ..components.__microcontroller import externalBoard
from ..utils.__utils_objects import AVAILABLE_TOPICS, SENSORS_TOPICS, PEER
from ..components.__audioManager import AudioManager

class OperatorNode( Node ):

        def __init__( self, **kwargs):

            super().__init__("controller", namespace=f"{PEER.USER.value}_0")

            self.EnableAudio = True
            self.forceStopFromGsc = False

            self._address = ""
            self._sensors_id = None
            self._pub_propulsion = None
            self._pub_direction = None
            self._pub_orientation = None
            self._pub_pantilt = None
            self._pub_sensor = None

            self.controllerOrientationMultiplier = 1 #use it to invert direction
            self.controllerPropulsionMultiplier = 1 

            self.MPU_TiltMultiplier = 1
            self.MPU_PanMultiplier = 1

            self._board = None
            self._audioManager = None

            self._propulsion_default = 45 #default percentage of thrust
            self._propulsion_max = 70
            self._propulsion = self._propulsion_default 
            self._direction = 0
            self._orientation = 0
  
            self._delta_yaw = 0
            self._delta_roll = 0
            self._delta_pitch = 0

            self._sensor_yaw = 0
            self._sensor_pitch =0
            self._sensor_roll =0
            
            self._angleX = 90
            self._angleZ = 90

            self.isGamePlayEnable = False

            self.wheelAudioTick = 0
            self.wheelAudioThreshold = 30

            self.mpu_keys = set([
                SENSORS_TOPICS.PITCH.value,
                SENSORS_TOPICS.ROLL.value,
                SENSORS_TOPICS.YAW.value,
                SENSORS_TOPICS.DELTA_PITCH.value,
                SENSORS_TOPICS.DELTA_ROLL.value,
                SENSORS_TOPICS.DELTA_YAW.value
            ]
            )
            self.start()

        @property
        def panTiltThreshold(self):
            return 10
        
        def start(self):

            self.get_local_ip()
            self._declare_parameters()
            self._init_publishers()
            self._init_subscribers()
            self._init_component()


        def reset( self ):

            self._propulsion = self._propulsion_default 
            self._direction = 0
            self._orientation = 0
            self._angleX = 90
            self._angleZ = 90

        def _declare_parameters( self ):
            self.declare_parameter("peer_index", 0)


        def get_local_ip( self ):

            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            try:

                s.connect(('8.8.8.8', 80))
                self._address = s.getsockname()[0]
            except socket.error:
                # Si la connexion échoue, nous renvoyons l'adresse IP de la machine locale
                self._address = socket.gethostbyname(socket.gethostname())
            finally:
                s.close()

        def _init_component(self):
            
            self._board = externalBoard( self._board_datas )
            self.reset()

            self._board._enable()

            if self.EnableAudio is True: 
                self._audioManager = AudioManager()
                self._audioManager._enable()

            #add listener to watchdog to start and stop ambiance background


        def _init_publishers( self ):

            self._pub_propulsion  = self.create_publisher(
                UInt16, 
                AVAILABLE_TOPICS.PROPULSION.value,
                qos_profile=qos_profile_sensor_data
            )
            
            self._pub_propulsion

            self._pub_direction = self.create_publisher(
                Int8, 
                AVAILABLE_TOPICS.DIRECTION.value,
                qos_profile=qos_profile_sensor_data
            )
            
            self._pub_direction

            self._pub_orientation  = self.create_publisher(
                Int8, 
                AVAILABLE_TOPICS.ORIENTATION.value,
                qos_profile=qos_profile_sensor_data
            )
            
            self._pub_orientation

            self._pub_pantilt = self.create_publisher(
                Vector3,
                AVAILABLE_TOPICS.PANTILT.value,
                qos_profile=qos_profile_sensor_data
            )

            self._pub_pantilt


            self._pub_sensor = self.create_publisher(
                String,
                AVAILABLE_TOPICS.SENSOR.value,
                qos_profile = qos_profile_sensor_data
            )

            self._pub_sensor   


        def _init_subscribers( self ):
            
            self._sub_master = self.create_subscription(
                String,
                f"/{PEER.MASTER.value}/{AVAILABLE_TOPICS.HEARTBEAT.value}",
                self.OnMasterPulse,
                qos_profile=qos_profile_sensor_data
            )
            
            self._sub_master  # prevent unused variable warning

            self._sub_drone_sensor = self.create_subscription(
                String,
                f"/{PEER.DRONE.value}_{self.get_parameter('peer_index').value}/{AVAILABLE_TOPICS.SENSOR.value}",
                self.OnDroneDatas,
                qos_profile=qos_profile_sensor_data
            )

            self._sub_drone_sensor


        def _update_propulsion( self ):
            
            prop_msg = UInt16()
            prop_msg.data = np.clip(self._propulsion, self._propulsion_default, self._propulsion_max) * self.controllerPropulsionMultiplier

            self._pub_propulsion.publish( prop_msg )


        def _update_direction( self ):
            
            if self.forceStopFromGsc is False:

                self._direction = np.clip( self._direction, -1, 1 )
            
                if( self._direction == 0):
                    self.reset()

                #if self._audioManager is not None:
                #    self._audioManager.stop_music()


                dir_msg = Int8()
                dir_msg.data = int(self._direction)

                self._pub_direction.publish( dir_msg )
        


        def _update_orientation( self, increment = 0 ):
            
            if increment != 0:
                msg = Int8()
                msg.data = int(increment * self.controllerOrientationMultiplier )

                self._pub_orientation.publish( msg )

                self._updateWheelAudio( increment )


        def _updateWheelAudio( self, increment ): 

            self.wheelAudioTick += abs(increment)

            if self.wheelAudioTick >= self.wheelAudioThreshold: 
                self.wheelAudioTick = 0

                if( self.isGamePlayEnable is True ):
                    if self._audioManager is not None:
                        self._audioManager.play_sfx("wheel")


        def _update_panoramic( self, pan = 90, tilt=90):

            update_tilt = tilt
            update_pan = pan

            vec = Vector3()
            
            vec.x = float( update_tilt )
            vec.z = float( update_pan )

            self._pub_pantilt.publish( vec )


        def _board_datas( self, json_datas ): 
            
            datas = json_datas

            if SENSORS_TOPICS.ORIENTATION.value in datas:
                self.OnNewOrientation(datas[SENSORS_TOPICS.ORIENTATION.value])
            
            if SENSORS_TOPICS.PROPULSION.value in datas:
                self.OnNewPropulsion(datas[SENSORS_TOPICS.PROPULSION.value])

            if SENSORS_TOPICS.SHORT_PRESS.value in datas and SENSORS_TOPICS.LONG_PRESS.value in datas:
                self.OnButtonPress( 
                    datas[SENSORS_TOPICS.SHORT_PRESS.value], 
                    datas[SENSORS_TOPICS.LONG_PRESS.value] 
                )

            if self.mpu_keys.issubset( datas.keys()):   
                self.OnMPUDatas(
                    pitch=datas[SENSORS_TOPICS.PITCH.value],
                    roll=datas[SENSORS_TOPICS.ROLL.value],
                    yaw=datas[ SENSORS_TOPICS.YAW.value ],
                    delta_p = datas[ SENSORS_TOPICS.DELTA_PITCH.value ],
                    delta_r=datas[ SENSORS_TOPICS.DELTA_ROLL.value ],
                    delta_y=datas[ SENSORS_TOPICS.DELTA_YAW.value ]
                )

            self._send_sensors_datas(json_datas)

        def OnNewOrientation( self, increment ):

            self._update_orientation( increment )


        def OnNewPropulsion( self, updateLevelIncrement ): 

            if self._direction != 0:

                increment = self._propulsion + updateLevelIncrement
                
                if self._direction > 0:
                    increment = math.floor( np.clip( increment, 25, 100 ) ) 
                elif self._direction < 0 :
                    increment = math.floor( np.clip( increment, 25, 50 ) ) 

                if increment != self._propulsion:

                    self._propulsion = increment
                    self._update_propulsion()


        def OnButtonPress( self, shortPress = False, longPress = False ):
            
            if longPress is True:

                if self._direction != -1:
                    self._direction = -1
                    self._update_direction()
                    
                    if( self.isGamePlayEnable is True ):
                        if self._audioManager is not None:
                            self._audioManager.play_sfx("bell")

            if shortPress is True:

                if self._direction == 0:
                    self._direction = 1
                else:
                    self._direction = 0
                
                if( self.isGamePlayEnable is True ):  
                    if self._audioManager is not None:
                        self._audioManager.play_sfx("bell")

                self._update_direction()


        def OnMPUDatas( self, pitch=0, roll=0, yaw=0, delta_p = 0, delta_r=0, delta_y=0 ):

            self._sensor_yaw = yaw
            self._sensor_pitch = pitch
            self._sensor_roll = roll

            self._delta_p = delta_p
            self._delta_r =  delta_r
            self._delta_y = delta_y

            #angle_aroundX = np.clip(90 - yaw, 0, 180)
            #angle_aroundY = np.clip( 90 - delta_y, 0,180 )
            #angle_aroundZ = np.clip( 90 + delta_p, 0,180 )
            
            
            angleX = np.clip(90 + roll * self.MPU_TiltMultiplier , 0, 180) 
            angleZ = np.clip( self._angleZ * self.MPU_PanMultiplier + delta_p, 0,180 )

            if abs(angleX - self._angleX ) >= self.panTiltThreshold or abs(angleZ - self._angleZ) >= self.panTiltThreshold:
           
                self._angleX = angleX
                self._angleZ = angleZ
                self._update_panoramic(pan=self._angleZ, tilt = self._angleX  )


        def _send_sensors_datas( self, sensor_json ):
            
            sensor_msg = String()
            
            if self._sensors_id is None:
                self._sensors_id = self.get_parameter("peer_index").value

            sensor_json[f"{SENSORS_TOPICS.IP}"] = f"{self._address}"
            #self.get_logger().info(sensor_json[f"{SENSORS_TOPICS.IP}"] )
            sensors_datas = {
                "index" : self._sensors_id,
                "datas" : sensor_json
            }

            sensor_msg.data = json.dumps( sensors_datas )

            self._pub_sensor.publish( sensor_msg )


        def OnDroneDatas( self, msg ):
            
            drone_sensors = json.loads( msg.data )

            if( "index" in drone_sensors and "datas" in drone_sensors ):
    
                sensor_datas = drone_sensors["datas"]

                for topic in sensor_datas:

                    if(topic == SENSORS_TOPICS.DIRECTION  ):
                        self.droneDirection = sensor_datas[topic]
     


        def OnMasterPulse( self, msg ):

            master_pulse = json.loads( msg.data )
            
            if "peers" in master_pulse: 

                peers = master_pulse["peers"]
                peerUpdate = f"peer_{self.get_parameter('peer_index').value}"

                if peerUpdate in peers: 

                    statusUpdate = peers[peerUpdate]

                    if "stop" in statusUpdate: 

                        self.forceStopFromGsc = statusUpdate["stop"]

                        if self.forceStopFromGsc is True and self._direction != 0:
                            self._direction = 0

                    if "enable" in statusUpdate and "playtime" in statusUpdate:

                        self.isGamePlayEnable = statusUpdate["enable"]
                        
                    else:
                    
                        self.isGamePlayEnable = False   
                        self._direction = 0
                        self._update_direction()

            else:
                    self.isGamePlayEnable = False 
                    self._direction = 0
                    self._update_direction()
                    
            if self._audioManager is not None:
                self._audioManager.gameplayMusic(self.isGamePlayEnable, self._direction )
            
        def exit(self):

            print("shutdown controller")   



def main(args=None):

    rclpy.init(args=args)

    controller_node = None 

    try:

        controller_node = OperatorNode()

        rclpy.spin( controller_node )

    except Exception as e:
        print( "an exception has been raised while spinning controller node : ", e )
        exception_type, exception_object, exception_traceback = sys.exc_info()
        filename = exception_traceback.tb_frame.f_code.co_filename
        line_number = exception_traceback.tb_lineno

        print("Exception type: ", exception_type)
        print("File name: ", filename)
        print("Line number: ", line_number)

    except KeyboardInterrupt:
        print("user force interruption")
        
    finally:

        if controller_node is not None:
            controller_node.exit()

        rclpy.try_shutdown()


if __name__ == '__main__':
    main()