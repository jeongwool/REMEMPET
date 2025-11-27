import os

import io

import time

import base64

import requests 

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

from flask_sqlalchemy import SQLAlchemy

from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user

from flask_bcrypt import Bcrypt

from dotenv import load_dotenv

from PIL import Image



import google.generativeai as genai

from deep_translator import GoogleTranslator



load_dotenv()

app = Flask(__name__)

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev_key_123')

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'

app.config['UPLOAD_FOLDER'] = 'static/pet_images'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)



db = SQLAlchemy(app)

bcrypt = Bcrypt(app)

login_manager = LoginManager(app)

login_manager.login_view = 'login'



GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")



if not GOOGLE_API_KEY or not STABILITY_API_KEY:

    print("⚠️ WARNING: API 키가 설정되지 않았습니다.")



genai.configure(api_key=GOOGLE_API_KEY)

CHAT_MODEL_NAME = "models/gemini-pro-latest"



STABILITY_API_HOST = "https://api.stability.ai"

STABILITY_ENGINE_ID = "stable-diffusion-xl-1024-v1-0"



class User(db.Model, UserMixin):

    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(20), unique=True, nullable=False)

    password = db.Column(db.String(60), nullable=False)

    pets = db.relationship('Pet', backref='owner', lazy=True)



class Pet(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), nullable=False)

    breed = db.Column(db.String(100))

    color = db.Column(db.String(100))

    age = db.Column(db.String(50))

    favorite_food = db.Column(db.String(100))

    background = db.Column(db.String(100))

    image_file = db.Column(db.String(100), nullable=False, default='default.jpg')

    persona_prompt = db.Column(db.Text)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    chat_history = db.relationship('ChatHistory', backref='pet', lazy=True, cascade="all, delete-orphan")



class ChatHistory(db.Model):

    id = db.Column(db.Integer, primary_key=True)

    role = db.Column(db.String(10), nullable=False)

    content = db.Column(db.Text, nullable=False)

    pet_id = db.Column(db.Integer, db.ForeignKey('pet.id'), nullable=False)



@login_manager.user_loader

def load_user(user_id):

    return User.query.get(int(user_id))



def translate(text):

    if not text: return ""

    try:

        return GoogleTranslator(source='auto', target='en').translate(text=text)

    except:

        return text



def generate_image_rest(prompt):

    url = f"{STABILITY_API_HOST}/v1/generation/{STABILITY_ENGINE_ID}/text-to-image"

    headers = {

        "Content-Type": "application/json",

        "Accept": "application/json",

        "Authorization": f"Bearer {STABILITY_API_KEY}"

    }

    body = {

        "text_prompts": [{"text": prompt}],

        "cfg_scale": 7,

        "height": 1024,

        "width": 1024,

        "samples": 1,

        "steps": 30,

    }

    

    response = requests.post(url, headers=headers, json=body)

    

    if response.status_code != 200:

        raise Exception(f"Stability API Error: {response.status_code} - {response.text}")



    data = response.json()

    image_data = base64.b64decode(data["artifacts"][0]["base64"])

    return image_data



@app.route("/")

@app.route("/home")

@login_required

def home():

    pets = Pet.query.filter_by(owner=current_user).all()

    return render_template('index.html', pets=pets)



@app.route("/chat/<int:pet_id>")

@login_required

def chat_page(pet_id):

    pet = Pet.query.get_or_404(pet_id)

    if pet.owner != current_user:

        flash('권한이 없습니다.', 'danger')

        return redirect(url_for('home'))

    history_db = ChatHistory.query.filter_by(pet_id=pet.id).order_by(ChatHistory.id.asc()).all()

    return render_template('chat.html', pet=pet, history=history_db)



@app.route("/register", methods=['GET', 'POST'])

def register():

    if current_user.is_authenticated: return redirect(url_for('home'))

    if request.method == 'POST':

        hashed_pw = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')

        user = User(username=request.form['username'], password=hashed_pw)

        db.session.add(user)

        db.session.commit()

        login_user(user)

        return redirect(url_for('home'))

    return render_template('register.html')



@app.route("/login", methods=['GET', 'POST'])

def login():

    if current_user.is_authenticated: return redirect(url_for('home'))

    if request.method == 'POST':

        user = User.query.filter_by(username=request.form['username']).first()

        if user and bcrypt.check_password_hash(user.password, request.form['password']):

            login_user(user, remember=True)

            return redirect(url_for('home'))

        else:

            flash('로그인 실패.', 'danger')

    return render_template('login.html')



@app.route("/logout")

@login_required

def logout():

    logout_user()

    return redirect(url_for('login'))



@app.route("/api/create_pet", methods=['POST'])

@login_required

def api_create_pet():

    try:

        data = request.json

        name = data.get('name')

        breed = data.get('breed')

        color = data.get('color')

        age = data.get('age')

        food = data.get('favorite_food')

        bg = data.get('background')



        t_breed, t_color, t_food, t_bg = translate(breed), translate(color), translate(food), translate(bg)

        prompt = f"A cute, happy {t_color} {t_breed} dog, {age} years old, eating {t_food}, in {t_bg}. 3D Pixar style, character portrait."



        image_bytes = generate_image_rest(prompt)

        

        image = Image.open(io.BytesIO(image_bytes))

        filename = f"pet_{current_user.id}_{int(time.time())}.png"

        image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))



        persona_prompt = f"당신은 반려견 '{name}'입니다. 종:{breed}, 색:{color}, 나이:{age}, 음식:{food}. 반말을 쓰고 다정하게 대해주세요."

        new_pet = Pet(

            name=name, breed=breed, color=color, age=age, 

            favorite_food=food, background=bg, image_file=filename, 

            persona_prompt=persona_prompt, user_id=current_user.id

        )

        db.session.add(new_pet)

        db.session.commit()

        

        model = genai.GenerativeModel(CHAT_MODEL_NAME)

        chat = model.start_chat(history=[

            {"role": "user", "parts": [persona_prompt]}, 

            {"role": "model", "parts": [f"안녕! 나 {name}야!"]}

        ])

        first_msg = chat.send_message(f"'{name}'으로서 반말로 따뜻한 첫인사를 해줘.").text

        

        db.session.add(ChatHistory(role='model', content=first_msg, pet_id=new_pet.id))

        db.session.commit()



        return jsonify({

            'success': True, 

            'pet_id': new_pet.id, 

            'first_message': first_msg,

            'pet_name': new_pet.name

        })

    

    except Exception as e:

        print(f"생성 오류: {e}")

        return jsonify({'success': False, 'error': str(e)}), 500



@app.route("/api/chat/<int:pet_id>", methods=['POST'])

@login_required

def api_chat(pet_id):

    pet = Pet.query.get_or_404(pet_id)

    if pet.owner != current_user: return jsonify({'error': '권한 없음'}), 403

    

    msg = request.json.get("message", "").strip()

    if not msg: return jsonify({'reply': "..."})



    history_db = ChatHistory.query.filter_by(pet_id=pet.id).order_by(ChatHistory.id.asc()).all()

    gemini_history = [{"role": "user", "parts": [pet.persona_prompt]}, {"role": "model", "parts": ["알았어!"]}]

    for h in history_db:

        gemini_history.append({"role": h.role, "parts": [h.content]})



    try:

        model = genai.GenerativeModel(CHAT_MODEL_NAME)

        chat = model.start_chat(history=gemini_history)

        reply = chat.send_message(msg).text

        

        db.session.add(ChatHistory(role='user', content=msg, pet_id=pet.id))

        db.session.add(ChatHistory(role='model', content=reply, pet_id=pet.id))

        db.session.commit()

        

        return jsonify({'reply': reply})

    except Exception as e:

        return jsonify({'error': str(e)}), 500



@app.route("/api/delete_pet/<int:pet_id>", methods=['POST'])

@login_required

def api_delete_pet(pet_id):

    pet = Pet.query.get_or_404(pet_id)

    if pet.owner != current_user: return jsonify({'success': False}), 403

    try:

        ChatHistory.query.filter_by(pet_id=pet.id).delete()

        db.session.delete(pet)

        db.session.commit()

        return jsonify({'success': True})

    except Exception as e:

        return jsonify({'success': False, 'error': str(e)}), 500



if __name__ == '__main__':

    with app.app_context():

        db.create_all() 

    app.run(debug=True, port=5000)
