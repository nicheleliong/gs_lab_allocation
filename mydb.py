# run this file to set up the databse
import mysql.connector # mysql-connector-python

dataBase = mysql.connector.connect(
    host = 'localhost',
    user = 'root',
    passwd = 'nicheleliong'
)

#prepare a cursor object
cursorObject = dataBase.cursor()

#Create a database (change name of database accordingly)
cursorObject.execute("CREATE DATABASE gs_allocation")

print("All Done!")