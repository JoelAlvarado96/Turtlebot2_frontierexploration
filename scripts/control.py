#!/usr/bin/env python

import sys
import rospy, time, tf
import math as math
from nav_msgs.msg import Odometry, OccupancyGrid
from final_project.srv import *
from geometry_msgs.msg import Twist, Point
from std_msgs.msg import Bool
from tf.transformations import euler_from_quaternion
from sensor_msgs.msg import LaserScan
from threading import Thread
import Queue

WHEEL_RADIUS = 0.035
DISTANCE_BETWEEN_WHEELS = 0.23
ROBOT_RADIUS = 0.2
POS_TOLERANCE = 0.02
ANGLE_TOLERANCE = 0.05
POS_REQUEST_RATE = 30.0
PROCESS_COSTMAP = False
ROTATE_AROUND_GRANULARITY = 9
LINEAR_VELOCITY = 0.15
OBSTACLE_DETECTION_THRESHOLD = 0.75

#Impelements PID controller
class PID:
    #Initializes PID
    def __init__(self, P=1, I=0.0001, D=0.001, Derivator=0, Integrator=0, outMax=3, outMin=-3):
        self.Kp = P
        self.Ki = I
        self.Kd = D
        self.Derivator = Derivator
        self.Integrator = Integrator
        self.outMax = outMax
        self.outMin = outMin

    #Updates pid based on the error provided / actualiza el PID segun el error proporcionado
    def update(self, error):
        self.P_value = self.Kp * error
        self.D_value = self.Kd * (error - self.Derivator)
        self.Derivator = error

        self.Integrator = self.Integrator + error

        self.I_value = self.Integrator * self.Ki

        if self.I_value > self.outMax:
            self.I_value = self.outMax
            self.Integrator -= error
        elif self.I_value < self.outMin:
            self.I_value = self.outMin
            self.Integrator -= error

        PID = self.P_value + self.I_value + self.D_value

        if PID > self.outMax:
            PID = self.outMax
        elif PID < self.outMin:
            PID = self.outMin

        return PID

    def reset(self):
        self.Integrator = 0
        self.Derivator = 0

#A class that is responsible for the robot control and publishing messages to the robot/
#Una clase que se encarga del control del robot y la publicación de mensajes al robot
class RobotControl:
    def __init__(self, publisher, update_rate, rotate_around_granularity, angle_tolerance, pos_tolerance):
        self.publisher = publisher
        self.update_rate = update_rate
        self.rotate_around_granularity = rotate_around_granularity
        self.angle_tolerance = angle_tolerance
        self.pos_tolerance = pos_tolerance

    #Rotate 360 degrees /gira
    def rotateAround(self):
        for i in range(0, self.rotate_around_granularity):
            self.rotate(2 * math.pi/self.rotate_around_granularity)

    #Commands the robot to go to the position specified / Ordena al robot que vaya a la posición especificada
    def goToPositionInAStraightLine(self, speed, destination_x, destination_y):
        # adding current_theta is done in rotate(angle)
        angle = math.atan2(destination_y - current_y, destination_x - current_x)
        self.rotateToAngle(angle)

        print "Driving to: %f, %f" % (destination_x, destination_y)
        self.goToPosition(speed, destination_x, destination_y)

   #Goes to the desired position / Va a la posición deseada
    def goToPosition(self, speed, destination_x, destination_y):
        yaw_control = PID(P=0.8, I=0.05, D=0.001, Derivator=0, Integrator=0, outMin=-1.5, outMax=1.5)

        prev_destination_angle = math.atan2(destination_y - current_y, destination_x - current_x)
        initialDistance = (math.sqrt((destination_x - current_x)**2 + (destination_y - current_y)**2))/2 #Usamos la mitad de la distancia a la frotera
        initial_x = current_x
        initial_y = current_y

        rate = rospy.Rate(self.update_rate)

        while ((current_x > destination_x + self.pos_tolerance or current_x < destination_x - self.pos_tolerance) \
            or (current_y > destination_y + self.pos_tolerance or current_y < destination_y - self.pos_tolerance)) \
            and not (math.sqrt((current_x - initial_x)**2 + (current_y - initial_y)**2))/2 > initialDistance:
            if isNewTrajectoryReady or obstacleEncountered:
                break

            destination_angle = math.atan2(destination_y - current_y, destination_x - current_x)

            #If there is a new set point, then reset the derivator and integrator
            #Si hay un nuevo punto de ajuste, restablezca el derivador y el integrador
            if destination_angle != prev_destination_angle:
                prev_destination_angle = destination_angle
                yaw_control.reset()

            error = RobotControl.normalize_angle(destination_angle - current_theta)

            feed = yaw_control.update(error)

            self.publishTwist(speed, feed)

            rate.sleep()

        self.publishTwist(0, 0)

    #Accepts an angle and makes the robot rotate around it./ 
    #Acepta un ángulo y hace que el robot gire a su alrededor.
    def rotate(self, angle):
        sum = current_theta + angle
        destination_angle = RobotControl.normalize_angle(sum)

        self.rotateToAngle(destination_angle)

    #Rotates to the specified angle in the global coordinate frame
    #Gira al ángulo especificado en el marco de coordenadas global
    def rotateToAngle(self, destination_angle):
        yaw_control = PID(P=0.8, I=0.03, D=0.001, Derivator=0, Integrator=0, outMin=-1.3, outMax=1.3)

        error = RobotControl.normalize_angle(destination_angle - current_theta)

        rate = rospy.Rate(self.update_rate)

        while abs(error) > self.angle_tolerance:
            if isNewTrajectoryReady or obstacleEncountered:
                break

            error = RobotControl.normalize_angle(destination_angle - current_theta)

            feed = yaw_control.update(error)

            self.publishTwist(0, feed)

            rate.sleep()

        self.publishTwist(0, 0)

    #Publishes twist
    def publishTwist(self, x_vel, angular_vel):
        twist = Twist()
        twist.linear.x = x_vel
        twist.linear.y = 0
        twist.linear.z = 0
        twist.angular.x = 0
        twist.angular.y = 0
        twist.angular.z = angular_vel

        self.publisher.publish(twist)

    # This function accepts two wheel velocities and a time interval.
    #Esta función acepta dos velocidades de rueda y un intervalo de tiempo.
    def spinWheels(self, u1, u2, t):
        x_vel = (WHEEL_RADIUS / 2) * (u1 + u2)
        angular_vel = (WHEEL_RADIUS / DISTANCE_BETWEEN_WHEELS) * (u1 - u2)

        startTime = time.time()

        self.publishTwist(x_vel, angular_vel)

        while time.time() - startTime < t:
            self.publishTwist(x_vel, angular_vel)

        self.publishTwist(0, 0)

    #Normalizes angle, so that it only takes values in range [-pi, pi)
    #Normaliza el ángulo, por lo que solo toma valores en el rango [-pi, pi)
    @staticmethod
    def normalize_angle(angle):
        return math.atan2(math.sin(angle), math.cos(angle))

#Requests the current position as a transform at rate of 10Hz
#Solicita la posición actual como una transformación a una frecuencia de 10 Hz
def request_pos_at_rate(frequency):
    global current_x
    global current_y
    global current_theta
    global receivedInitPos

    tfListener = tf.TransformListener() #transforma el espacio del robot en celdas

    rate = rospy.Rate(frequency)

    while not rospy.is_shutdown() and not exit:
        try:
            (trans, rot) = tfListener.lookupTransform('map', 'base_footprint', rospy.Time(0))
            current_x = trans[0]
            current_y = trans[1]

            q = [rot[0], rot[1], rot[2], rot[3]]

            roll, pitch, yaw = euler_from_quaternion(q)

            current_theta = yaw
        except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
            continue

        if not receivedInitPos:
            receivedInitPos = True

        rate.sleep()

#Callback function that processes the OccupancyGrid message.
#Función de devolución de llamada que procesa el mensaje OccupancyGrid.
def mapCallback(mapMessage):
    global receivedNewMap
    global map

    #Store the mapMessage as global in order for the requestTrajectory function to use it.
    #Almacene el mensaje del mapa como global para que la función de solicitud de trayectoria lo utilice.
    map = mapMessage

    receivedNewMap = True

#Callback function that processes the OccupancyGrid message.
#Función de devolución de llamada que procesa el mensaje OccupancyGrid.
def costmapCallback(costMapMessage):
    global costMap
    global receivedNewCostMap

    #Store the costmapMessage as global in order for the requestTrajectory function to use it.
    #Almacene el costmapMessage como global para que la función requestTrajectory lo use.
    costMap = costMapMessage

    receivedNewCostMap = True

#The callback function that updates the scan message
def scanCallback(scanMessage):
    global scanMessageQueue

    if not scanMessageQueue.empty():
        scanMessageQueue.get()

    scanMessageQueue.put(scanMessage)

#Processes the scan message received
def scanProcessing():
    global obstacleEncountered
    global wasLocalGoalDefined

    while scanMessageQueue.empty():
        rospy.sleep(0.1)

    while not rospy.is_shutdown() and not exit:
        while not obstacleEncountered and wasLocalGoalDefined:
            scanMessage = scanMessageQueue.get()

            minRange = 9999
            for rangeValue in scanMessage.ranges:
                if not math.isnan(rangeValue) and rangeValue < minRange:
                    minRange = rangeValue

            if minRange < OBSTACLE_DETECTION_THRESHOLD:
                dest_angle = math.atan2(localGoalY - current_y, localGoalX - current_x)
                # print "Dest angle: %f" % dest_angle

                scanAngle_lowerBound = RobotControl.normalize_angle(current_theta + scanMessage.angle_min)
                # print "ScanAngle_lowerBound: %f" % scanAngle_lowerBound
                scanAngle_upperBound = RobotControl.normalize_angle(current_theta + scanMessage.angle_max)
                # print "ScanAngle_upperBound: %f" % scanAngle_upperBound

                diff1 = RobotControl.normalize_angle(scanAngle_upperBound - dest_angle)
                diff2 = RobotControl.normalize_angle(dest_angle - scanAngle_lowerBound)

                # print diff1, diff2, diff1 >= 0 and diff2 >= 0

                if diff1 >= 0 and diff2 >= 0:
                    # print "Angle is within lower and upper bounds!"

                    dest_distance = math.sqrt((localGoalY - current_y)**2 + (localGoalX - current_x)**2)
                    # print "Dest distance: %f" % dest_distance
                    dest_angle_from_lower_bound = diff2
                    # print "dest_angle_from_lower_bound: %f" % dest_angle_from_lower_bound
                    # dest_angle_index = int(dest_angle_from_lower_bound/scanMessage.angle_increment)

                    for i in range(0, len(scanMessage.ranges)):
                        current_range = scanMessage.ranges[i]
                        # print i, current_range
                        if not math.isnan(current_range) and current_range < (dest_distance + ROBOT_RADIUS):
                            # print "Found that range that has index %d and value %f is less than dest_distance %f" % (i, current_range, dest_distance)

                            current_angle = abs(RobotControl.normalize_angle(dest_angle_from_lower_bound - i * scanMessage.angle_increment))
                            # print "Current angle: %f" % current_angle
                            passage_width = current_range * math.sin(current_angle)
                            # print "Passage width: %f" % passage_width

                            if passage_width < ROBOT_RADIUS:
                                # print "Obstacle encountered!"
                                obstacleEncountered = True
                                break

        rospy.sleep(0.1)

#Processes the received map.
def requestTrajectory(goalPos):
    global receivedNewMap
    global receivedNewCostMap
    global isNewTrajectoryReady
    global previousTrajectory
    global trajectory
    global reachedGoal
    global abnormalTermination
    global costMap

    while not reachedGoal and not rospy.is_shutdown() and not exit:
        if not receivedNewMap:
            continue
        else:
            #Reset flag
            if receivedNewMap:
                receivedNewMap = False
            # if receivedNewCostMap:
            #     receivedNewCostMap = False

        #Request new trajectory
        initPos = Point()
        initPos.x = current_x
        initPos.y = current_y

        #create a stub for costmap
        if not PROCESS_COSTMAP:
            costMap = OccupancyGrid()

        try:
            trajectory = getTrajectory(initPos, goalPos, map, Bool(data=PROCESS_COSTMAP), costMap)
        except rospy.ServiceException, e:
            print "getTrajectory() call failed: %s" % e
            reachedGoal = True # Just exit the execution of this trajectory to be able to navigate to a new goal
            isNewTrajectoryReady = True # Interrupt execution of the current trajectory
            abnormalTermination = True
            break

        #Check if the previous trajectory was defined
        try:
            previousTrajectory
        except NameError:
            previousTrajectory = trajectory
            isNewTrajectoryReady = True
        else:
            #Check if the previous trajectory is the same as the received trajectory
            if previousTrajectory.path.poses != trajectory.path.poses:
                isNewTrajectoryReady = True

#This function sequentially calls methods to perform a trajectory. / Esta función llama secuencialmente a métodos para realizar una trayectoria. 
def executeTrajectory(control):
    global reachedGoal
    global isNewTrajectoryReady
    global localGoalX
    global localGoalY
    global wasLocalGoalDefined
    global obstacleEncountered
    global abnormalTermination

    #Wait for the initial trajectory
    while not isNewTrajectoryReady:
        pass

    while not reachedGoal and not rospy.is_shutdown() and not exit:
        counter = 0
        oldTrajectoryPoses = trajectory.path.poses
        isNewTrajectoryReady = False

        for point in oldTrajectoryPoses:
            localGoalX = point.pose.position.x
            localGoalY = point.pose.position.y

            wasLocalGoalDefined = True

            control.goToPositionInAStraightLine(LINEAR_VELOCITY, localGoalX, localGoalY)

            if obstacleEncountered:
                print "Obstacle encountered! Rotating to let the map process the obstacle..."
                reachedGoal = True # Just exit the execution of this trajectory to be able to navigate to a new goal
                abnormalTermination = True
                return

            if isNewTrajectoryReady:
                break

            if counter >= (len(oldTrajectoryPoses) - 1):
                reachedGoal = True

            counter += 1

    wasLocalGoalDefined = False

#Executes the main task of exploring the world around / Ejecuta la tarea principal de explorar el mundo que lo rodea. 
def exploreEnvironment():
    global abnormalTermination
    global isNewTrajectoryReady
    global wasLocalGoalDefined
    global obstacleEncountered

    teleop_pub = rospy.Publisher('/cmd_vel_mux/input/teleop', Twist, queue_size=5)
    control = RobotControl(teleop_pub, POS_REQUEST_RATE, ROTATE_AROUND_GRANULARITY, ANGLE_TOLERANCE, POS_TOLERANCE)

    while not rospy.is_shutdown() and not exit:
        if abnormalTermination:
            #reset variables on abnormal termination
            abnormalTermination = False
            isNewTrajectoryReady = False
            wasLocalGoalDefined = False
            obstacleEncountered = False

        #1) Rotate 360 degrees to initially explore the world around
        print "=====> Started new iteration <====="
        print "1) Rotating 360."
        control.rotateAround()

        #2) Request new centroid
        print "2) Requesting new centroid."
        try:
            currentPos = Point(x=current_x, y=current_y, z=0)
            centroidResponse = getCentroid(map, currentPos)
        except rospy.ServiceException, e:
            print "getCentroid() call failed: %s" % e
            abnormalTermination = True
            isNewTrajectoryReady = True
            continue

        if not centroidResponse.foundCentroid.data:
            #We are done, exit.
            break

        #3) Go to a new goal
        print "3) Navigating to the centroid."
        navigateToGoal(control, centroidResponse.centroid)
        print "======>   Ended iteration   <====="

#Navigates the robot to the goal position
def navigateToGoal(control, goal):
    global reachedGoal

    reachedGoal = False

    Thread(target=requestTrajectory, name="requestTrajectory() Thread", args=[goal]).start()
    executeTrajectory(control)

#Main function
if __name__ == "__main__":
    #Initialize the new node
    rospy.init_node('control')

    #Wait for trajectory service to start up
    print "Waiting for getTrajectory() service to start up...",
    rospy.wait_for_service('getTrajectory')
    global getTrajectory
    getTrajectory = rospy.ServiceProxy('getTrajectory', Trajectory)
    print "DONE"
    # trajectory = getCentroid(initPos, goalPos, map, processCostMap, costMap)
    # initPos.pose.pose.position
    print "Waiting for getCentroid() service to start up...",
    #Wait for centroid service to start up
    rospy.wait_for_service('getCentroid')
    global getCentroid
    getCentroid = rospy.ServiceProxy('getCentroid', Centroid)
    print "DONE"
    # centroid = getCentroid(map)

    #Flags that indicate if the initial or goal positions were received
    global receivedInitPos
    global receivedNewMap
    global receivedNewCostMap
    global exit

    #Flag
    global isNewTrajectoryReady
    global reachedGoal
    global abnormalTermination
    global obstacleEncountered

    obstacleEncountered = False

    #Flag that indicate whether the local goal was defined
    global wasLocalGoalDefined

    #Trajectory
    global trajectory
    global map

    wasLocalGoalDefined = False
    reachedGoal = False
    isNewTrajectoryReady = False
    receivedInitPos = False
    receivedNewMap = False
    receivedNewCostMap = True
    abnormalTermination = False
    exit = False
    obstacleEncountered = False

    global scanMessageQueue
    scanMessageQueue = Queue.Queue()

    #Subscribe to map updates
    map_sub = rospy.Subscriber('/map', OccupancyGrid, mapCallback, queue_size=1)
    scan_sub = rospy.Subscriber('/scan', LaserScan, scanCallback, queue_size=1)
    # costmap_sub = rospy.Subscriber('/move_base/local_costmap/costmap', OccupancyGrid, costmapCallback, queue_size=1)
    #Start requesting position in background
    Thread(target=request_pos_at_rate, name="Request_pos_at_rate Thread", args=[POS_REQUEST_RATE]).start()
    Thread(target=scanProcessing, name="Request_pos_at_rate Thread").start()

    print "Waiting for the initial position from tf...",

    while not receivedInitPos or not receivedNewMap or not receivedNewCostMap:
        rospy.sleep(.1)
        pass

    print "DONE"

    print "Started exploration."

    # control = RobotControl(rospy.Publisher('/cmd_vel_mux/input/teleop', Twist, queue_size=5), POS_REQUEST_RATE, ROTATE_AROUND_GRANULARITY, ANGLE_TOLERANCE, POS_TOLERANCE)
    # control.rotate(math.pi)

    exploreEnvironment()

    print "Done with exploration. Exiting...",
    exit = True
    print "DONE"


