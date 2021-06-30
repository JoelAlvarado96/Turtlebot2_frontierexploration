# Turtlebot2_frontierexploration
Codigo para mapear un lugar usando un robot Turtlebot2, para mapear se usa SLAM y selección de fronteras.

El presente archivo es un codigo para un Turtlebot2, este codigo te permite mapear un área en interiores usando SLAM y algoritmo de optimización para elegir la ruta mas efectiva, tomando como puntos de referencia las fronteras. Se usó como guía el repositorio https://github.com/ujasmandavia/turtlebot-2-autonomous-navigation y se realizó modificaciones al usar la distancia media desde el robot hasta la frontera y un giro de 360 grados para obtener mejor odometría

Para descargar los paquetes de ejecutables debes configurar tu espacio de trabajo en ROS, usando las siguientes líneas:
mkdir -p /catkin_ws/src
cd /catkin_ws/
catkin_make
Pasos para usas los ejecutables en el robot

roslaunch turtlebot\_bringup minimal.launch

roslaunch turtlebot\_navigation gmapping\_demo.launch

roslaunch turtlebot\_rviz\_launchers view\_navigation.launch

Para los ultimos 3 comandos debemos meternos a la carpetas donde fue guardado el repositorio en los 3 ultimos terminales

cd /catkin_ws/

y escribir el comando para actualizar los ejecutables de dicha carpeta en cada uno

source devel/setup.bash

Luego colocar en cada terminal

roslaunch final\_project final\_project.launch

rosrun final\_project mapping.py

rosrun final\_project control.py
