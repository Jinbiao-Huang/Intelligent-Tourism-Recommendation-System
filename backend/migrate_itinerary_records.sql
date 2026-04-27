-- Add itinerary_records table for admin trip record monitoring
CREATE TABLE IF NOT EXISTS itinerary_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  destination VARCHAR(255) NOT NULL,
  days INT NOT NULL,
  has_edited_destination TINYINT(1) NOT NULL DEFAULT 0,
  edited_from VARCHAR(255),
  edited_to VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  INDEX idx_itinerary_records_user_id (user_id),
  INDEX idx_itinerary_records_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
