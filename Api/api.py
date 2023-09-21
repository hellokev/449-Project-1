import collections
import contextlib
import logging.config
import sqlite3
import typing
import datetime

from fastapi import FastAPI, Depends, Response, HTTPException, status
from pydantic import BaseModel
from pydantic_settings import BaseSettings

class Settings(BaseSettings, env_file=".env", extra="ignore"):
    database: str
    logging_config: str

def get_db():
    with contextlib.closing(sqlite3.connect(settings.database)) as db:
        db.row_factory = sqlite3.Row
        yield db

def get_logger():
    return logging.getLogger(__name__)

settings = Settings()
app = FastAPI()

logging.config.fileConfig(settings.logging_config, disable_existing_loggers=False)

@app.get("/")
async def message():
    """Returns a welcome message."""
    return {"message": "Project 1"}


# Task: List available classes
# Example: http://localhost:5000/student/available_classes
@app.get("/student/available_classes")
def get_available_classes(db: sqlite3.Connection = Depends(get_db)):
    classes = db.execute("""
                SELECT class_code, section_number, class_name, i_first_name, i_last_name, current_enrollment, max_enrollment
                FROM Class, Instructor
                WHERE current_enrollment < max_enrollment
                AND c_instructor_id = instructor_id
            """)    
    return {"classes": classes.fetchall()}


# Task: Attempt to enroll in a class
# Example: http://localhost:5000/student/enroll_in_class/?student_id=11111111&class_code=CPSC449&section_number=01
@app.get("/student/enroll_in_class")
def get_available_classes(student_id: str, class_code:str, section_number:str, db: sqlite3.Connection = Depends(get_db)):
    # Check to see if student already enrolled
    student_is_enrolled = db.execute("""
        SELECT *
        FROM Enroll
        WHERE e_student_id=? 
        AND e_class_code=? 
        AND e_section_number=?
    """, (student_id, class_code, section_number)).fetchall()

    if student_is_enrolled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Student already enrolled"
        )
    
    # Check to see if student already on waitlist
    student_on_waitlist = db.execute("""
        SELECT *
        FROM Waitlist
        Where w_student_id=?
        AND w_class_code=?
        AND w_section_number=?
    """, (student_id, class_code, section_number)).fetchall()

    if student_on_waitlist:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Student already on waitlist"
        )
    
    # Get class information
    class_details = db.execute("""
        SELECT max_enrollment, current_enrollment, max_waitlist, current_waitlist
        FROM Class
        WHERE class_code=?
        AND section_number=?
    """, (class_code, section_number)).fetchall()[0]
    
    # If the classes current enrollment is less than the max enrollment then enroll the student into the class
    if class_details['current_enrollment'] < class_details['max_enrollment']:
        # Enroll the student into the class
        db.execute("""
            INSERT INTO Enroll (e_student_id, e_class_code, e_section_number)
            VALUES (?, ?, ?)
        """, (student_id, class_code, section_number))

        # Increment the number of students that are enrolled for the class
        db.execute("""
            UPDATE Class
            SET current_enrollment=current_enrollment + 1
            Where class_code=?
            AND section_number=?
        """, (class_code, section_number))

        return {"detail": "Student successfully enrolled in class"}

    else:

        # Put the student on the waitlist
        student_details = db.execute("""
            SELECT *
            FROM Student
            WHERE student_id=?
        """, (student_id,)).fetchall()[0]

        # Student reached the max number of classes they can be waitlisted for
        if student_details['num_waitlist'] >= 3:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Class enrollment full and student has exceeded their max number of waitlisted classes"
            )   
        
        # Add student the waitlist
        currentDateTime = datetime.datetime.now()
        db.execute("""
            INSERT INTO Waitlist (w_student_id, w_class_code, w_section_number, timestamp)
            VALUES (?, ?, ?, ?);
        """, (student_id, class_code, section_number, currentDateTime))

        # Increment the number of students on the class waitlist
        db.execute("""
            UPDATE Class
            SET current_waitlist=current_waitlist + 1
            WHERE class_code=?
            AND section_number=?
        """, (class_code, section_number))

        # Increment the number of classes the student is waitlisted for
        db.execute("""
            UPDATE Student
            SET num_waitlist=num_waitlist + 1
            WHERE student_id=?
        """, (student_id,))

        return {"detail": "Class enrollment full, Student added to waitlist"}
    