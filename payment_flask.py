import json, pycurl, os, time
from io import BytesIO
import dataset
import settings
from hashids import Hashids
from flask import Flask, render_template, request, redirect, url_for
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app)

hashids = Hashids(salt=settings.hash_salt)

print('Starting...')

db = dataset.connect('sqlite:///transactions.db')
trans_table = db['transactions']
wallet = settings.wallet
count = 0

def wallet_com(data):

        buffer = BytesIO()
        c = pycurl.Curl()
        c.setopt(c.URL, '127.0.0.1')
        c.setopt(c.PORT, 7076)
        c.setopt(c.POSTFIELDS, json.dumps(data))
        c.setopt(c.WRITEFUNCTION, buffer.write)

        output = c.perform()

        c.close()

        body = buffer.getvalue()
        parsed_json = json.loads(body.decode('iso-8859-1'))
        return parsed_json

def get_int_balance(xrb_address):
	balance_data = {'action' : 'account_balance', 'account' : xrb_address}
	parsed_json = wallet_com(balance_data)
	if parsed_json == 'error':
		return 'error'

	i_balance = int(parsed_json['balance']) / 1000000000000000000000000
	i_pending = int(parsed_json['pending']) / 1000000000000000000000000

	# Once the customer sends a send block it can't be reveresed - we can therefore accept pending balance
	#even before we have actually processed and sent our receive block
	total_balance = i_balance + i_pending
	return total_balance

@app.route("/")
def start():
	return render_template('start.html')

@app.route("/gen_hash", methods=['POST'])
def gen_hash():
	if request.method == 'POST':
		amount = request.form['amount']
		transaction_id = request.form['transaction_id']
		hashid = hashids.encode(int(amount), int(transaction_id))
		print(hashid)
		#return 'Data: %s %s %s' % (amount, transaction_id, hashid)
		return redirect(url_for('run_payment', hash=hashid))

@app.route("/payment/<hash>")
def run_payment(hash):
	try:
		if trans_table.find_one(final_hash=str(hash)):
			print('Already registered')
			transaction_data = trans_table.find_one(final_hash=str(hash))
			print(transaction_data)
			return render_template('payment.html', hash=transaction_data['final_hash'], xrb_address=transaction_data['xrb_address'], amount=transaction_data['amount'])

		else:
			hash_ints = hashids.decode(hash)
			print(hash_ints)
			amount = hash_ints[0]
			transaction_id = hash_ints[1]
			#Generate new account
			data = { "action": "account_create", "wallet": wallet }
			parsed_json = wallet_com(data)
			new_account = parsed_json['account']
			print(new_account)
			#Add to database
			trans_table.insert(dict(final_hash=str(hash), xrb_address=new_account, registered=0, amount=amount, transaction_id=transaction_id))

			#return 'User %s %s %s' % (hash, amount, transaction_id)
			return render_template('payment.html', hash=str(hash), xrb_address=str(new_account), amount=str(amount))
	except:
		return 'Error with hash'

@socketio.on('poll_balance', namespace='/test')
def test_message(message):
	print(message['data'])
	hash = str(message['data'])
	print('Hash: %s' % hash)
	#message_json = json.loads(message)
	print('data poll balance %d' % time.time())
	if trans_table.find_one(final_hash=hash):
		print('Found')
		balance_details = trans_table.find_one(final_hash=hash)
		#print(balance_details)
		xrb_address = balance_details['xrb_address']
		print(xrb_address)
		current_balance = get_int_balance(xrb_address)
		emit('balance', {'data': current_balance})
	else:
		print('Error with poll')

@socketio.on('connect', namespace='/test')
def test_connect():
	print('data connect')
	emit('my response', {'data': 'Connected'})

@socketio.on('disconnect', namespace='/test')
def test_disconnect():
	print('data disconnect')
	print('Client disconnected')

if __name__ == '__main__':
	socketio.run(app)
