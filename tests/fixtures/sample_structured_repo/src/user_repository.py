TABLE_NAME = "users"


def find_user_by_email(email: str):
    return db.execute(
        "SELECT * FROM users WHERE email = ?",
        [email],
    )


def update_account_status(user_id: str, status: str):
    return db.execute(
        "UPDATE users SET account_status = ? WHERE id = ?",
        [status, user_id],
    )
