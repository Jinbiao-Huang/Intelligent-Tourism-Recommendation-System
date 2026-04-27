-- Add route_plans table for saving route planning results
CREATE TABLE IF NOT EXISTS route_plans (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  origin_address VARCHAR(255),
  destination_address VARCHAR(255),
  origin_lnglat VARCHAR(64) NOT NULL,
  destination_lnglat VARCHAR(64) NOT NULL,
  mode VARCHAR(32) NOT NULL,
  distance INT DEFAULT 0,
  duration INT DEFAULT 0,
  cost DECIMAL(10, 2) DEFAULT 0,
  steps JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
