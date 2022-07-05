# rockblock2mav
RockBlock to MAVLink gateway.

Simple Python script for sending and receiving MAVLink messages using the RockBlock SBD modems.

This gateway runs on the GCS, and will send/recieve MAVLink messages between the GCS and RockBlock servers.

Due to bandwidth constraints (50 bytes per message) MAVLink 1 is used, as it uses slightly less bytes per message
compared to MAVLink2.

For messages GCS -> Vehicle:
GCS -> rockblock2mav.py -> ROCK7 website -> Iridium Gateway -> Iridium Satellite -> Rockblock modem -> Vehicle

For messages Vehicle -> GCS:
Vehicle -> Rockblock modem -> Iridium satellite -> Iridium Gateway -> Rock7 website -> Adafuit.io feed -> rockblock2mav.py -> GCS

This is a work in progress!
