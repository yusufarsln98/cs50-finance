import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# import datetime to current time
from datetime import datetime

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    get_cash = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
    cash = get_cash[0]['cash']

    portfolio = db.execute("SELECT symbol, shares FROM portfolio WHERE user_id=:user_id", user_id=session["user_id"])

    total_estate = cash
    for stock in portfolio:
        result = lookup(stock['symbol'])
        price = result['price']
        name = result['name']
        float_total = stock['shares'] * price
        total = usd(float_total)
        stock.update({'name': name, 'price': price, 'total': total})
        total_estate += float_total

    return render_template("index.html", portfolio=portfolio, cash=usd(cash), total_estate=usd(total_estate))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():

    if request.method == "POST":

        get_symbol = request.form.get("symbol")
        get_shares = request.form.get("shares")

        if not get_symbol:
            return apology("Enter a symbol!", 400)
        if not get_shares:
            return apology("Enter number of shares!", 400)

        if not get_shares.isnumeric() or not get_shares.isdecimal():
            return apology("Enter a valid decimal for shares!", 400)

        quote = lookup(get_symbol)

        if not quote:
            return apology("Enter a valid symbol!", 400)

        # set values
        price = quote['price']
        name = quote['name']
        symbol = quote['symbol']
        shares = int(get_shares)

        # find cost of transaction that wants to be done
        cost = shares * price

        # check if user has enough cash for transaction
        row = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])
        if cost > row[0]["cash"]:
            return apology("Can Not Afford!", 400)

        # set ramaning money
        remaining = row[0]["cash"] - cost
        # update cash amount in users database
        db.execute("UPDATE users SET cash=:remaining WHERE id=:id", remaining=remaining, id=session["user_id"])

        # Add a transaction
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, date) VALUES (:user_id, :symbol, :shares, :price, :date)",
                   user_id=session["user_id"], symbol=symbol.upper(), shares=shares, price=price, date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        # find if it was already exist in the portfolio if the user
        current = db.execute("SELECT shares FROM portfolio WHERE user_id=:user_id AND symbol=:symbol",
                             user_id=session["user_id"], symbol=symbol.upper())

        # if it is, update, otherwise, insert
        if current:
            db.execute("UPDATE portfolio SET shares=shares+:new_shares WHERE user_id=:user_id AND symbol=:symbol",
                       user_id=session["user_id"], symbol=symbol.upper(), new_shares=shares)
        else:
            db.execute("INSERT INTO portfolio (user_id, symbol, shares) VALUES (:user_id, :symbol, :shares)",
                       user_id=session["user_id"], symbol=symbol.upper(), shares=shares)

        return redirect(url_for("index"))

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    transactions = db.execute("SELECT * FROM transactions WHERE user_id=:user_id", user_id=session["user_id"])
    for transaction in transactions:
        price_in_usd = usd(transaction['price'])
        transaction.update({'price_in_usd': price_in_usd})
    return render_template("history.html", transactions=transactions)


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

        quote = lookup(request.form.get("symbol"))
        # If stock does not exist
        if not quote:
            return apology("Invalid Symbol", 400)
        else:
            return render_template("quoted.html", quote=quote)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not username:
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not password:
            return apology("must provide password", 400)

        # Ensure confirmation was submitted
        elif not confirmation:
            return apology("must provide password again", 400)

        # Ensure both passwords are same
        if password != confirmation:
            return apology("Password and confirmation does not matched!", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # If username is taken, apology to the user.
        if len(rows) == 1:
            return apology("This username has been taken before!", 400)

        # hash the password to store it in database
        password_hash = generate_password_hash(password)
        register = db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", username=username, hash=password_hash)

        # According to registration or, log in, there can be a breadcrumb.

        # Remember which user has registered.
        session["user_id"] = register

        return redirect(url_for("index"))
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        get_symbol = request.form.get("symbol")
        get_shares = request.form.get("shares")

        if not get_symbol:
            return apology("Please select a stock!")
        if not get_shares:
            return apology("Please enter a share!")

        # lookup the price from symbol
        quote = lookup(get_symbol)
        price = quote['price']
        symbol = quote['symbol']
        shares_to_sell = int(get_shares)

        if shares_to_sell > db.execute("SELECT shares FROM portfolio WHERE user_id=:user_id AND symbol=:symbol", user_id=session["user_id"], symbol=symbol)[0]['shares']:
            return apology("Not enough stocks!")

        # find worth of transaction that wants to be done
        worth = shares_to_sell * price

        # update cash amount in users database
        db.execute("UPDATE users SET cash=cash+:worth WHERE id=:id", worth=worth, id=session["user_id"])

        # Add a transaction
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, date) VALUES (:user_id, :symbol, :shares_to_sell, :price, :date)",
                   user_id=session["user_id"], symbol=symbol, shares_to_sell=shares_to_sell * -1, price=price, date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        db.execute("UPDATE portfolio SET shares=shares-:shares_to_sell WHERE user_id=:user_id AND symbol=:symbol",
                   user_id=session["user_id"], symbol=symbol.upper(), shares_to_sell=shares_to_sell)

        # Delete non-shares
        db.execute("DELETE FROM portfolio WHERE shares=0")

        return redirect(url_for("index"))
    else:
        my_stocks = db.execute("SELECT symbol, shares FROM portfolio WHERE user_id=:user_id",
                               user_id=session["user_id"])
        return render_template("sell.html", stocks=my_stocks)


@app.route("/changepassword", methods=["GET", "POST"])
@login_required
def changepassword():
    """Change password"""
    if request.method == "POST":
        # Take password and confirmation and set it as new password.
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        if not password or not confirmation:
            return apology("must provide password/confirmation!", 403)

        if password != confirmation:
            return apology("Password and confirmation does not matched!", 403)

        password_hash = generate_password_hash(password)
        db.execute("UPDATE users SET hash=:hash WHERE id=:id", hash=password_hash, id=session["user_id"])

        return redirect(url_for("index"))
    else:
        return render_template("changepassword.html")