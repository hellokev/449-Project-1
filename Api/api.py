import collections
import contextlib
import logging.config
import sqlite3
import typing
import datetime
import json

from fastapi import FastAPI, Depends, Response, Request, HTTPException, status
from pydantic import BaseModel
from pydantic_settings import BaseSettings

class Class(BaseModel):
    class_code: str
    section_number: str
    class_name: str
    department: str
    auto_enrollment: bool
    max_enrollment: int
    current_enrollment: int
    max_waitlist: int
    current_waitlist: int
    c_instructor_id: str

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

# ---------------------- Additional -----------------------------

# Example: http://localhost:5000/all_classes
@app.get("/all_classes")
def get_available_classes(db: sqlite3.Connection = Depends(get_db)):
    classes = db.execute("""
                SELECT *
                FROM Class
            """)    
    return {"classes": classes.fetchall()}

# Example: http://localhost:5000/student/student_details
@app.get("/student/student_details")
def get_available_classes(student_id: str, db: sqlite3.Connection = Depends(get_db)):

    # Get student details
    student_details = db.execute("""
        SELECT *
        FROM Student
        WHERE student_id=?
    """, (student_id,)).fetchall()[0]

    return {"student": student_details}

# Example: http://localhost:5000/student/student_enrollment
@app.get("/student/student_enrollment")
def get_available_classes(student_id: str, db: sqlite3.Connection = Depends(get_db)):

    # Get student details
    student_enrollment = db.execute("""
        SELECT *
        FROM Enroll
        WHERE e_student_id=?
    """, (student_id,)).fetchall()

    return {"enrollment": student_enrollment}


# ---------------------- Tasks -----------------------------

# Task 1: Student can list all available classes
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

# Task 2: Student can attempt to enroll in a class
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

        # Commit the changes
        db.commit()

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

        # Commit the changes
        db.commit()

        return {"detail": "Class enrollment full, Student added to waitlist"}

# Task 3: Student can drop a class
# Example: http://localhost:5000/student/drop_class/?student_id=11111111&class_code=CPSC449&section_number=01
@app.get("/student/drop_class")
def drop_class(student_id: str, class_code:str, section_number:str, db: sqlite3.Connection = Depends(get_db)):

    # Check to see if student already enrolled
    student_is_enrolled = db.execute("""
        SELECT *
        FROM Enroll
        WHERE e_student_id=? 
        AND e_class_code=? 
        AND e_section_number=?
    """, (student_id, class_code, section_number)).fetchall()

    # If they are enrolled, unroll them
    if student_is_enrolled:
        db.execute("""
        DELETE 
        FROM Enroll 
        Where e_student_id=?
        AND e_class_code=?
        AND e_section_number=?
        """, (student_id, class_code, section_number))

        # Decrement number of students enrolled
        db.execute("""
        UPDATE Class
        SET current_enrollment = current_enrollment - 1
        Where class_code=?
        AND section_number=?
        AND current_enrollment > 0
        """, (class_code, section_number))

        # Add them to drop list
        db.execute("""
        INSERT INTO Dropped (d_student_id, d_class_code, d_section_number)
        VALUES(?, ?, ?);
        """, (student_id, class_code, section_number))

        # Commit the changes
        db.commit()

        return {"detail": "Class successfully dropped."}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot drop class, student is not enrolled."
        )   

    
# Task 4: Instructor can view current enrollment for their classes
# Example: GET https://localhost:5000/instructor/enrollment/?instructor_id=100
@app.get("/instructor/enrollment")
def drop_class(instructor_id: str, db: sqlite3.Connection = Depends(get_db)):
    enrollment = db.execute("""
        SELECT student_id, s_first_name, s_last_name, class_code, section_number, class_name
        FROM Instructor, Class, Enroll, Student
        WHERE Instructor.instructor_id=?
        AND Instructor.instructor_id=Class.c_instructor_id
        AND  Class.class_code=Enroll.e_class_code
        AND Class.section_number=Enroll.e_section_number
        AND Enroll.e_student_id=student_id
        """, (instructor_id,)).fetchall()
    
    return {"enrollment": enrollment}

# Task 5: Instructor can view students who have dropped the class
# Example: GET https://localhost:5000/instructor/enrollment/?instructor_id=100
@app.get("/instructor/dropped")
def drop_class(instructor_id: str,  class_code:str, section_number:str, db: sqlite3.Connection = Depends(get_db)):
    dropped = db.execute("""
        SELECT student_id, s_first_name, s_last_name, class_code, section_number
        FROM Instructor, Class, Dropped, Student
        WHERE Instructor.instructor_id=?
        AND Class.class_code=?
        AND Class.section_number=?
        AND Instructor.instructor_id=Class.c_instructor_id
        AND  Class.class_code=Dropped.d_class_code
        AND Class.section_number=Dropped.d_section_number
        AND Dropped.d_student_id=student_id
        """, (instructor_id, class_code, section_number)).fetchall()
    
    return {"dropped": dropped}

# Task 6: Instructor can drop students administratively (e.g. if they do not show up to class)
# Example: http://localhost:5000/instructor/drop_student/?student_id=11111111&class_code=CPSC449&section_number=01
@app.get("/instructor/drop_student")
def drop_class(student_id: str, class_code:str, section_number:str, db: sqlite3.Connection = Depends(get_db)):

    # Check to see if student already enrolled
    student_is_enrolled = db.execute("""
        SELECT *
        FROM Enroll
        WHERE e_student_id=? 
        AND e_class_code=? 
        AND e_section_number=?
    """, (student_id, class_code, section_number)).fetchall()

    # If they are enrolled, unroll them
    if student_is_enrolled:
        db.execute("""
        DELETE 
        FROM Enroll 
        Where e_student_id=?
        AND e_class_code=?
        AND e_section_number=?
        """, (student_id, class_code, section_number))

        # Decrement number of students enrolled
        db.execute("""
        UPDATE Class
        SET current_enrollment = current_enrollment - 1
        Where class_code=?
        AND section_number=?
        AND current_enrollment > 0
        """, (class_code, section_number))

        # Add them to drop list
        db.execute("""
        INSERT INTO Dropped (d_student_id, d_class_code, d_section_number)
        VALUES(?, ?, ?);
        """, (student_id, class_code, section_number))

        # Commit the changes
        db.commit()

        return {"detail": "Student successfully dropped."}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot drop class, student is not enrolled."
        )   
    
# Task 7: Registrar can add new classes and sections
# Example: POST https://localhost:5000/registrar/new_class
# body: {
#     "class_code": "CPSC335",
#     "section_number": "01",
#     "class_name": "Algorithm Engineering",
#     "department": "Computer Science",
#     "auto_enrollment": TRUE,
#     "max_enrollment": 30,
#     "current_enrollment": 0,
#     "max_waitlist": 15,
#     "current_waitlist": 0,
#     "c_instructor_id": "100",
# }
@app.post("/registrar/new_class")
def drop_class(new_class: Class, request: Request, db: sqlite3.Connection = Depends(get_db)):

    c = dict(new_class)
    
    class_exists = db.execute("""
                SELECT *
                FROM Class
                WHERE class_code=:class_code
                AND section_number=:section_number
            """, c).fetchall()
    
    if class_exists:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Class already exists."
        )   

    db.execute("""
        INSERT INTO Class (class_code, section_number, class_name, department, auto_enrollment, max_enrollment, current_enrollment, max_waitlist, current_waitlist, c_instructor_id)
        VALUES (:class_code, :section_number, :class_name, :department, :auto_enrollment, :max_enrollment, :current_enrollment, :max_waitlist, :current_waitlist, :c_instructor_id)
        """, c)
    
    # Commit the changes
    db.commit()
    
    return {"detail": "New class successfully added."}