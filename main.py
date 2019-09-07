from flask import Flask, request
import telegram
from telegram.ext import CommandHandler, MessageHandler, Filters, Updater
import datetime
import pymongo


app = Flask(__name__)
bot = telegram.Bot(token="<TOKEN>")
mongo_client = pymongo.MongoClient("<MONGODB>")
db = mongo_client["tgbot"]
msg = db["tg-pending"]
timer = db["tg-timer"]

defaultDestruct = -1
destroyTimers = {}

@app.route('/status')
def show_status():
    return 'Pending to be deleted: '+str(msg.count_documents({}))+' messages. <br>'+str(destroyTimers)

@app.route('/process_queue')
def process_queue():
    timeNow = datetime.datetime.now().timestamp()
    deleted = 0
    while True:
        result = msg.find_one_and_delete({ 'expiry': {"$lt": timeNow} })
        if result is None:
            break
        else:
            msg_deleted = bot.delete_message(result["chat_id"], result["msg_id"])
            deleted = deleted + 1
    
    return 'Deleted '+str(deleted)+' messages.'

@app.route('/hook',methods=['POST'])
def webhook_handler():
    if request.method == "POST":
        update = telegram.Update.de_json(request.get_json(force=True), bot)
        dispatcher.process_update(update)
    return 'ok'

def check_user_admin(bot, chat_id, user_id):
    member = bot.get_chat_member(chat_id, user_id)
    return (member.status in ["creator", "administrator"])

def check_bot_admin(bot, chat_id):
    self_id = bot.get_me().id
    admins = bot.get_chat_administrators(chat_id)
    admin_flag = False
    for admin in admins:
        if str(admin.user.id) == str(self_id):
            admin_flag = True
    return admin_flag

def status(bot, update):
    chat_id = update.message.chat_id
    output = '# of pending messages: '+str(msg.count_documents({}))+"\n"
    output = output + '# of groups: '+str(timer.count_documents({}))+"\n"
    timeNow = datetime.datetime.now().timestamp()
    maxExpiry = msg.find_one(sort=[("expiry", 1)])["expiry"]
    minExpiry = msg.find_one(sort=[("expiry", -1)])["expiry"]
    output = output + 'Next expiry: '+str(int((maxExpiry-timeNow)/60))+" mins\n"
    output = output + 'Last expiry: '+str(int((minExpiry-timeNow)/60))+" mins\n\n"
    
    output = output + '<Timers>'+"\n"
    chats = timer.find({},{'chat_id':1, 'timer':1, '_id':0})
    for tmp in chats:
        output = output + tmp['chat_id'] + ': ' +str(tmp['timer'])+"\n"
    bot.send_message(chat_id=chat_id, text=output)

def off_timer(bot, update):
    global destroyTimers
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    if check_user_admin(bot, chat_id, user_id):
        destroyTimers[str(chat_id)] = -1
        timer.replace_one({'chat_id': str(chat_id)}, {'chat_id': str(chat_id), 'timer': -1}, True)
        bot.send_message(chat_id=chat_id, text='Self-destruct timer is switched off.')
    else:
        bot.send_message(chat_id=chat_id, text='Bot settings can only be changed by group admins.')

def set_timer(bot, update, args):
    global destroyTimers
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    if not check_bot_admin(bot, chat_id):
        bot.send_message(chat_id=chat_id, text='DelHistoryBot must be promoted to group admin. Only admins can delete messages. Follow these instructions to add admin:')
        bot.send_photo(chat_id=chat_id, photo="https://i.imgur.com/90E0DO0.png")
    elif not check_user_admin(bot, chat_id, user_id):
        bot.send_message(chat_id=chat_id, text='Bot settings can only be changed by group admins.')
    else:
        try:
            due = int(args[0])
            if due > 2875:
                bot.send_message(chat_id=chat_id, text='Sorry, must be within 48 hours.')
            else:
                destroyTimers[str(chat_id)] = due
                timer.replace_one({'chat_id': str(chat_id)}, {'chat_id': str(chat_id), 'timer': due}, True)
                bot.send_message(chat_id=chat_id, text='Self-destruct timer is set to '+str(due)+' minutes.')
        except (IndexError, ValueError):
            bot.send_message(chat_id=chat_id, text='Usage: /destroytimer <minutes>')

def msg_handler(bot, update):
    global destroyTimers
    chat_id = update.message.chat_id
    msg_id = update.message.message_id
    dt = update.message.date
    #dt = datetime.datetime.now()
    chat_timer = defaultDestruct
    if (str(chat_id) in destroyTimers):
        chat_timer = destroyTimers[str(chat_id)]
    if chat_timer == defaultDestruct:
        result = timer.find_one({'chat_id': str(chat_id)})
        if not result is None:
            chat_timer = result['timer']
            destroyTimers[str(chat_id)] = chat_timer
    if (chat_timer>0):
        e = dt.timestamp()+chat_timer*60
        msg.insert_one({'chat_id': chat_id, 'msg_id': msg_id, 'expiry': e})

updater = Updater(bot=bot,workers=0)
dispatcher = updater.dispatcher
dispatcher.add_handler(CommandHandler("status", status))
dispatcher.add_handler(CommandHandler("destroyoff", off_timer))
dispatcher.add_handler(CommandHandler("destroytimer", set_timer, pass_args=True))
dispatcher.add_handler(MessageHandler(Filters.all, msg_handler))

def main():
    app.run()

if __name__ == '__main__':
    main()