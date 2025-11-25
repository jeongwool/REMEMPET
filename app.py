import os
import io
import time 
import base64
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
from PIL import Image

import google.generativeai as genai
from stability_sdk import client
import stability_sdk.interfaces.gooseai.generation.generation_pb2 as generation
from deep_translator import GoogleTranslator

# --- 1. 기본 설정 ---
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default_secret_key_for_dev_123')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['UPLOAD_FOLDER'] = 'static/pet_images' 
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True) 

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login' 


GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)
CHAT_MODEL_NAME = "models/gemini-pro-latest"

STABILITY_API_KEY = os.getenv("STABILITY_API_KEY")
stability_api = client.StabilityInference(
    key=STABILITY_API_KEY,
    verbose=True,
    engine="stable-diffusion-xl-1024-v1-0"
)

# --- 2. 데이터베이스 모델 ---
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

# --- 3. AI 헬퍼 함수 ---
def translate(text):
    if not text:
        return ""
    try:
        return GoogleTranslator(source='auto', target='en').translate(text=text)
    except Exception as e:
        print(f"번역 오류: {e}")
        return text

# --- 4. 웹페이지 라우트 ---
@app.route("/")
@app.route("/home")
@login_required
def home():
    pets = Pet.query.filter_by(owner=current_user).all()
    return render_template('index.html', pets=pets) 

@app.route("/chat/<int:pet_id>", methods=['GET'])
@login_required
def chat_page(pet_id):
    pet = Pet.query.get_or_404(pet_id)
    if pet.owner != current_user:
        flash('권한이 없습니다.', 'danger')
        return redirect(url_for('home'))
    
    history_db = ChatHistory.query.filter_by(pet_id=pet.id).order_by(ChatHistory.id.asc()).all()
    
    chat_session_history = []
    chat_session_history.append({"role": "user", "parts": [pet.persona_prompt]})
    chat_session_history.append({"role": "model", "parts": [f"알았어! 난 너의 다정한 친구, {pet.name}이야!"]})
    
    for entry in history_db:
        chat_session_history.append({"role": entry.role, "parts": [entry.content]})
        
    session[f'chat_history_{pet_id}'] = chat_session_history

    return render_template('chat.html', pet=pet, history=history_db)

@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        hashed_password = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
        user = User(username=request.form.get('username'), password=hashed_password)
        db.session.add(user)
        db.session.commit()
        login_user(user)  
        return redirect(url_for('home'))
    return render_template('register.html')

@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and bcrypt.check_password_hash(user.password, request.form.get('password')):
            login_user(user, remember=True)
            return redirect(url_for('home'))
        else:
            flash('로그인 실패. 이름과 비밀번호를 확인하세요.', 'danger')
    return render_template('login.html')

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- 5. AI 기능 API 엔드포인트 ---

@app.route("/api/create_pet", methods=['POST'])
@login_required
def api_create_pet():
    data = request.json
    name = data.get('name')
    breed = data.get('breed')
    color = data.get('color')
    age = data.get('age')
    favorite_food = data.get('favorite_food')
    background = data.get('background')

    try:
        t_breed = translate(breed)
        t_color = translate(color)
        t_food = translate(favorite_food)
        t_background = translate(background)
        
        prompt = (
            f"A highly detailed, realistic 3D Pixar style portrait of a cute {t_color} {t_breed} dog. "
            f"The dog is {age} years old, looking happy and smiling. "
            f"It is eating {t_food} in a {t_background} setting. "
            "Cinematic lighting, high quality, trending on artstation."
        )
        
        answers = stability_api.generate(
            prompt=prompt,
            steps=30, 
            cfg_scale=7.0,
            width=1024,  
            height=1024, 
            samples=1,  
        )

        image_bytes = None
        for resp in answers:
            for artifact in resp.artifacts:
                if artifact.finish_reason == generation.FILTER:
                    raise Exception("이미지가 안전 필터에 걸렸습니다. 다른 단어를 사용해보세요.")
                if artifact.type == generation.ARTIFACT_IMAGE:
                    image_bytes = artifact.binary
                    break
        if not image_bytes: raise Exception("Stability AI 이미지 생성 실패")

        image = Image.open(io.BytesIO(image_bytes))
        image_filename = f"pet_{current_user.id}_{int(time.time())}.png"
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
        image.save(image_path)
        
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        image_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")

        persona_prompt = f"당신은 이제부터 사용자의 반려견 '{name}'이야. 종은 {breed}이고, 색깔은 {color}이며, {age}의 나이였고, {favorite_food}를 가장 좋아했어. 너의 말투는 꼭 반말을 사용하며, 아주 다정하고 친한 친구처럼 말해줘. 존댓말은 절대 사용하면 안돼."

        new_pet = Pet(
            name=name, breed=breed, color=color, age=age, favorite_food=favorite_food, background=background,
            image_file=image_filename,
            persona_prompt=persona_prompt,
            user_id=current_user.id
        )
        db.session.add(new_pet)
        db.session.commit()
        
        model = genai.GenerativeModel(CHAT_MODEL_NAME)
        chat = model.start_chat(history=[
            {"role": "user", "parts": [persona_prompt]},
            {"role": "model", "parts": [f"알았어! 난 너의 다정한 친구, {new_pet.name}이야!"]}
        ])
        response = chat.send_message(f"'{name}'으로서 사용자에게 반말로 따뜻한 첫인사를 건네줘. 보고 싶었다는 내용을 포함해서.")
        first_message = response.text
        
        db.session.add(ChatHistory(role='model', content=first_message, pet_id=new_pet.id))
        db.session.commit()

        return jsonify({
            'success': True, 
            'pet_id': new_pet.id, 
            'image_b64': image_b64, 
            'first_message': first_message, 
            'pet_name': new_pet.name
        })
    
    except Exception as e:
        print(f"오류 상세: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/api/chat/<int:pet_id>", methods=['POST'])
@login_required
def api_chat(pet_id):
    pet = Pet.query.get_or_404(pet_id)
    if pet.owner != current_user:
        return jsonify({'error': '권한 없음'}), 403

    message = request.json.get("message", "").strip()
    if not message:
        return jsonify({'reply': "..."})
        

    history_db = ChatHistory.query.filter_by(pet_id=pet.id).order_by(ChatHistory.id.asc()).all()
    
    chat_session_history = [
        {"role": "user", "parts": [pet.persona_prompt]},
        {"role": "model", "parts": [f"알았어! 난 너의 다정한 친구, {pet.name}이야!"]}
    ]
    for entry in history_db:
        chat_session_history.append({"role": entry.role, "parts": [entry.content]})

    try:
        model = genai.GenerativeModel(CHAT_MODEL_NAME)
        chat = model.start_chat(history=chat_session_history)
        response = chat.send_message(message, request_options={'timeout': 30})
        reply = response.text
        
        db.session.add(ChatHistory(role='user', content=message, pet_id=pet.id))
        db.session.add(ChatHistory(role='model', content=reply, pet_id=pet.id))
        db.session.commit()
        
        return jsonify({'reply': reply})
    except Exception as e:
        print(f"채팅 오류: {e}")
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
