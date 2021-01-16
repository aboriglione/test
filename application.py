import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

from datetime import datetime

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db",
connect_args={'check_same_thread': False})

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    stocks = db.execute("SELECT * FROM holdings WHERE user_id = ?", session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id= ?", session["user_id"])
    cashusd = usd(cash[0]['cash'])

    grandtotal = 0

    for stock in stocks:
        price = lookup(stock['symbol'])['price']
        total = float(stock['amount']) * float(price)
        grandtotal += total

        db.execute("UPDATE holdings SET price= ?, total= ? WHERE user_id= ? AND symbol= ?",
                    usd(price), usd(total), session["user_id"], stock["symbol"])

    grandtotal += cash[0]["cash"]

    holdings = db.execute("SELECT * FROM holdings WHERE user_id = ?", session["user_id"])

    return render_template('index.html', holdings=holdings, cash=cashusd, grandtotal=usd(grandtotal))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        # apology if input is blank.
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)

        stock = lookup(request.form.get("symbol"))

        # apology if symbol does not exist.
        if not stock:
            return apology("symbol is invalid", 400)

        if request.form.get("shares").isdigit() == False:
            return apology("must be positive integer", 400)

        # if input is negative.
        if int(request.form.get("shares")) < 1:
            return apology("must be positive integer", 400)

        # Query database for cash in wallet
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])

        # Calculate cost
        cost = stock['price'] * int(request.form.get("shares"))

        # See if user can afford
        result = cash[0]['cash'] - cost
        if result < 0:
            return apology("you do not have enough cash to buy this stock", 400)

        # Update cash in users database
        db.execute("UPDATE users SET cash = ? WHERE id = ?", result, session["user_id"])

        db.execute("INSERT INTO transactions (user_id, stock, quantity, price, date) VALUES (?, ?, ?, ?, ?)",
                    session["user_id"], stock["symbol"], int(request.form.get("shares")), stock['price'], datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # Check if stock is already owned
        exists = db.execute("SELECT * FROM holdings WHERE user_id = ? AND symbol = ?",
                             session["user_id"], stock["symbol"])

        # If it is not already owned
        if not exists:
            db.execute("INSERT INTO holdings (user_id, symbol, name, amount, price) VALUES (?, ?, ?, ?, ?)",
            session["user_id"], stock["symbol"], stock["name"], int(request.form.get("shares")), stock["price"])

        else:# If user already owns amount
            old_amount = db.execute("SELECT amount FROM holdings WHERE user_id = ? AND symbol = ?",
                                    session["user_id"], stock["symbol"])
            new_amount = int(old_amount[0]["amount"]) + int(request.form.get("shares"))

            # Update amount
            db.execute("UPDATE holdings SET amount = ? WHERE user_id = ? AND symbol = ?",
            new_amount, session["user_id"], stock["symbol"]);

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)

        stock = lookup(request.form.get("symbol"))

        if not stock:
            return apology("symbol is invalid", 400)

        return render_template("quote.html", name=stock["name"], price=usd(stock["price"]), symbol=stock["symbol"])

    else:
        return render_template("quoted.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        else:
            # Query database for username
            rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
            # Ensure username does not exist
            if len(rows) == 1:
                return apology("username is already taken", 400)

        # Ensure password was submitted
        if not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure passwords match
        elif not request.form.get("password") == request.form.get("confirmation"):
            return apology("passwords did not match", 400)

        # Insert user into users table with hashed password
        username = request.form.get("username")
        hashed = generate_password_hash(request.form.get("password"))
        names = db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, hashed)

        # Query database for usernames for keeping logged in
        #names = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        #Remember which user has logged in
        #session["user_id"] = names

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":

        # apology if input is blank.
        if not request.form.get("shares"):
            return apology("must provide number of shares", 400)

        # if input is negative.
        if int(request.form.get("shares")) < 1:
            return apology("must be positive integer", 400)

        amount = db.execute("SELECT amount FROM holdings WHERE symbol = ? AND user_id = ?", request.form.get("symbol"), session["user_id"])
        print("amount", amount[0]['amount'])
        result = amount[0]['amount'] - int(request.form.get("shares"))
        print("amount", result)
        # if user does not have enough shares.
        if result <= 0:
            return apology("you do not own that many shares", 400)

        # Query database for cash in wallet
        cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])

        # Calculate yield
        stock = lookup(request.form.get("symbol"))
        income = stock['price'] * int(request.form.get("shares"))

        # New amount of cash user has
        new_cash = cash[0]['cash'] + income

        # Update cash in database
        db.execute("UPDATE users SET cash = ? WHERE id = ?", new_cash, session["user_id"]);

        old_amount = db.execute("SELECT amount FROM holdings WHERE user_id = ? AND symbol = ?",
                             session["user_id"], stock["symbol"])
        new_amount = int(old_amount[0]["amount"]) - int(request.form.get("shares"))

        # Update amount
        db.execute("UPDATE holdings SET amount = ? WHERE user_id = ? AND symbol = ?",
        new_amount, session["user_id"], stock["symbol"]);

        return redirect("/")


    else:
        stocks = db.execute("SELECT symbol FROM holdings WHERE user_id = ?", session["user_id"])

        return render_template("sell.html", stocks=stocks)




def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
