-- School Timetabling Database Schema

CREATE TABLE IF NOT EXISTS slots (
    id INT PRIMARY KEY,
    label VARCHAR(10) NOT NULL COMMENT '07:00, 08:00, etc.'
);

CREATE TABLE IF NOT EXISTS teachers (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS subjects (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255) NOT NULL
);

CREATE TABLE IF NOT EXISTS teacher_subjects (
    teacher_id VARCHAR(50) NOT NULL,
    subject_id VARCHAR(50) NOT NULL,
    PRIMARY KEY (teacher_id, subject_id),
    FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS classes (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    level VARCHAR(50) COMMENT 'fundamental, medio, etc.'
);

CREATE TABLE IF NOT EXISTS class_available_slots (
    class_id VARCHAR(50) NOT NULL,
    slot_id INT NOT NULL,
    PRIMARY KEY (class_id, slot_id),
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (slot_id) REFERENCES slots(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS requirements (
    id INT AUTO_INCREMENT PRIMARY KEY,
    class_id VARCHAR(50) NOT NULL,
    subject_id VARCHAR(50) NOT NULL,
    teacher_id VARCHAR(50) NOT NULL,
    hours_per_week INT NOT NULL,
    FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE CASCADE,
    FOREIGN KEY (subject_id) REFERENCES subjects(id) ON DELETE CASCADE,
    FOREIGN KEY (teacher_id) REFERENCES teachers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS schedule_runs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    cp_feasible BOOLEAN NOT NULL DEFAULT FALSE,
    soft_score_initial INT,
    soft_score_final INT,
    ls_iterations INT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS schedule_entries (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_id INT NOT NULL,
    class_id VARCHAR(50) NOT NULL,
    subject_id VARCHAR(50) NOT NULL,
    teacher_id VARCHAR(50) NOT NULL,
    day VARCHAR(20) NOT NULL,
    slot_id INT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES schedule_runs(id) ON DELETE CASCADE,
    FOREIGN KEY (class_id) REFERENCES classes(id),
    FOREIGN KEY (subject_id) REFERENCES subjects(id),
    FOREIGN KEY (teacher_id) REFERENCES teachers(id),
    FOREIGN KEY (slot_id) REFERENCES slots(id),
    UNIQUE KEY unique_class_slot (run_id, class_id, day, slot_id),
    UNIQUE KEY unique_teacher_slot (run_id, teacher_id, day, slot_id)
);
