
use csp_portal;

CREATE TABLE `admin_applynotifications` (
  `notification_id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `scheme_id` int NOT NULL,
  `message` varchar(500) NOT NULL,
  `notification_type` varchar(50) NOT NULL DEFAULT 'apply_click',
  `is_read` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`notification_id`),
  KEY `idx_notification_read` (`is_read`),
  KEY `idx_notification_time` (`created_at`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `admin_newnotifications` (
  `notification_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `message` varchar(500) NOT NULL,
  `notification_type` varchar(50) NOT NULL DEFAULT 'new_registration',
  `is_read` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`notification_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `admin_settings` (
  `setting_id` int NOT NULL AUTO_INCREMENT,
  `admin_id` int NOT NULL,
  `setting_key` varchar(100) NOT NULL,
  `setting_value` json NOT NULL,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`setting_id`),
  UNIQUE KEY `unique_admin_setting` (`admin_id`,`setting_key`),
  UNIQUE KEY `uq_admin_setting` (`admin_id`,`setting_key`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `admins` (
  `admin_id` int NOT NULL AUTO_INCREMENT,
  `full_name` varchar(100) NOT NULL,
  `date_of_birth` date NOT NULL,
  `gender` varchar(20) NOT NULL,
  `state` varchar(100) NOT NULL,
  `mobile_number` varchar(10) NOT NULL,
  `email` varchar(150) NOT NULL,
  `username` varchar(50) NOT NULL,
  `password_hash` varchar(255) NOT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`admin_id`),
  UNIQUE KEY `mobile_number` (`mobile_number`),
  UNIQUE KEY `email` (`email`),
  UNIQUE KEY `username` (`username`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `adminschemes` (
  `scheme_id` int NOT NULL AUTO_INCREMENT,
  `scheme_name` varchar(200) NOT NULL,
  `category` varchar(100) NOT NULL,
  `description` text NOT NULL,
  `eligibility_criteria` text,
  `benefits` text,
  `required_documents` text,
  `application_link` varchar(1000) DEFAULT NULL,
  `status` enum('Active','Inactive') NOT NULL DEFAULT 'Active',
  `deadline` date DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`scheme_id`)
) ENGINE=InnoDB AUTO_INCREMENT=4 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `applied_schemes` (
  `apply_id` bigint NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `scheme_id` int NOT NULL,
  `applied_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `status` enum('Pending','Approved','Rejected') NOT NULL DEFAULT 'Pending',
  `documents_count` int NOT NULL DEFAULT '0',
  `rejection_reason` text,
  PRIMARY KEY (`apply_id`),
  KEY `idx_apply_user` (`user_id`),
  KEY `idx_apply_scheme` (`scheme_id`),
  KEY `idx_apply_time` (`applied_at`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `education_details` (
  `education_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `qualification_level` varchar(50) DEFAULT NULL,
  `institution_name` varchar(150) DEFAULT NULL,
  `course_name` varchar(150) DEFAULT NULL,
  `field_of_study` varchar(150) DEFAULT NULL,
  `graduation_year` smallint DEFAULT NULL,
  `grade_or_cgpa` varchar(30) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`education_id`),
  UNIQUE KEY `uq_education_user` (`user_id`),
  CONSTRAINT `fk_education_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `employment_details` (
  `employment_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `employment_status` varchar(50) DEFAULT NULL,
  `employer_name` varchar(180) DEFAULT NULL,
  `job_title` varchar(120) DEFAULT NULL,
  `work_experience_years` decimal(4,1) DEFAULT NULL,
  `monthly_salary` decimal(12,2) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`employment_id`),
  UNIQUE KEY `uq_employment_user` (`user_id`),
  CONSTRAINT `fk_employment_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `income_details` (
  `income_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `annual_income` decimal(12,2) DEFAULT NULL,
  `income_source` varchar(100) DEFAULT NULL,
  `family_income` decimal(12,2) DEFAULT NULL,
  `ration_card_type` varchar(50) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`income_id`),
  UNIQUE KEY `uq_income_user` (`user_id`),



CREATE TABLE `location_details` (
  `location_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `address_line` varchar(255) DEFAULT NULL,
  `district` varchar(100) DEFAULT NULL,
  `city` varchar(100) DEFAULT NULL,
  `state` varchar(100) DEFAULT NULL,
  `pincode` varchar(10) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`location_id`),
  UNIQUE KEY `uq_location_user` (`user_id`),
  CONSTRAINT `fk_location_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `notifications` (
  `notification_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `title` varchar(180) NOT NULL,
  `message` text,
  `is_read` tinyint(1) NOT NULL DEFAULT '0',
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `notification_type` varchar(50) NOT NULL DEFAULT 'general',
  PRIMARY KEY (`notification_id`),
  KEY `idx_notifications_user_read_created`
    (`user_id`, `is_read`, `created_at`),
  CONSTRAINT `fk_notifications_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `personal_info` (
  `personal_info_id` int NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `full_name` varchar(100) DEFAULT NULL,
  `email` varchar(150) DEFAULT NULL,
  `mobile_number` varchar(15) DEFAULT NULL,
  `date_of_birth` date DEFAULT NULL,
  `gender` varchar(20) DEFAULT NULL,
  `state` varchar(100) DEFAULT NULL,
  `category` varchar(100) DEFAULT NULL,
  `district` varchar(100) DEFAULT NULL,
  `annual_income` decimal(12,2) DEFAULT NULL,
  `created_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`personal_info_id`),
  UNIQUE KEY `uq_personal_info_user` (`user_id`),
  CONSTRAINT `fk_personal_info_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE `saved_schemes` (
  `saved_id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `user_id` int NOT NULL,
  `scheme_id` int NOT NULL,
  `saved_at` timestamp NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`saved_id`),
  UNIQUE KEY `unique_user_scheme` (`user_id`, `scheme_id`),
  KEY `idx_saved_scheme` (`scheme_id`),
  CONSTRAINT `fk_saved_scheme`
    FOREIGN KEY (`scheme_id`) REFERENCES `adminschemes` (`scheme_id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_saved_user`
    FOREIGN KEY (`user_id`) REFERENCES `users` (`user_id`)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE `users` (
    `user_id` INT NOT NULL AUTO_INCREMENT,
    `full_name` VARCHAR(100) NOT NULL,
    `email` VARCHAR(150) DEFAULT NULL,
    `mobile_number` VARCHAR(15) DEFAULT NULL,
    `password_hash` VARCHAR(255) NOT NULL,
    `date_of_birth` DATE NOT NULL,
    `gender` VARCHAR(20) NOT NULL,
    `state` VARCHAR(100) NOT NULL,
    `created_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    `category` VARCHAR(100) DEFAULT NULL,
    `personal_info_id` INT DEFAULT NULL,
    PRIMARY KEY (`user_id`),
    UNIQUE KEY `email` (`email`),
    UNIQUE KEY `mobile_number` (`mobile_number`),
    KEY `fk_users_personal_info` (`personal_info_id`),
    CONSTRAINT `fk_users_personal_info`
        FOREIGN KEY (`personal_info_id`)
        REFERENCES `personal_info` (`personal_info_id`)
        ON DELETE SET NULL
) ENGINE=InnoDB
  AUTO_INCREMENT=3
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE `user_documents` (
    `document_id` INT NOT NULL AUTO_INCREMENT,
    `user_id` INT NOT NULL,
    `document_name` VARCHAR(100) NOT NULL,
    `original_filename` VARCHAR(255) NOT NULL,
    `stored_filename` VARCHAR(255) NOT NULL,
    `file_path` VARCHAR(500) NOT NULL,
    `file_size` BIGINT NOT NULL,
    `uploaded_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`document_id`),
    KEY `fk_user_documents_user` (`user_id`),
    CONSTRAINT `fk_user_documents_user`
        FOREIGN KEY (`user_id`)
        REFERENCES `users` (`user_id`)
        ON DELETE CASCADE
) ENGINE=InnoDB
  AUTO_INCREMENT=2
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE `user_notification_settings` (
    `setting_id` INT NOT NULL AUTO_INCREMENT,
    `user_id` INT NOT NULL,
    `setting_key` VARCHAR(100) NOT NULL,
    `setting_value` JSON NOT NULL,
    `updated_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`setting_id`),
    UNIQUE KEY `unique_user_setting` (`user_id`, `setting_key`)
) ENGINE=InnoDB
  AUTO_INCREMENT=8
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;


CREATE TABLE `viewed_schemes` (
    `view_id` INT NOT NULL AUTO_INCREMENT,
    `user_id` INT NOT NULL,
    `scheme_id` INT NOT NULL,
    `viewed_at` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`view_id`),
    KEY `idx_scheme_views_scheme` (`scheme_id`),
    KEY `idx_scheme_views_user` (`user_id`)
) ENGINE=InnoDB
  AUTO_INCREMENT=8
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE admin_sent_notifications (
    notification_id INT AUTO_INCREMENT PRIMARY KEY,
    admin_id INT NOT NULL,
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    notification_type VARCHAR(50) NOT NULL DEFAULT 'general',
    audience VARCHAR(20) NOT NULL DEFAULT 'all',
    category VARCHAR(100) DEFAULT NULL,
    recipients_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);