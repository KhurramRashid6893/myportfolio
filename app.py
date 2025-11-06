import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FileField
from wtforms.validators import DataRequired
from werkzeug.utils import secure_filename
import secrets

app = Flask(__name__)

# --- Configuration ---
app.config['SECRET_KEY'] = secrets.token_hex(16)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'instance', 'gallery.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 128 * 1024 * 1024  # 128 MB limit (for multiple images)
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'} # Added webp

# --- Passwords ---
GALLERY_PASSWORDS = {
    '123': 'public',
    'admin123': 'admin'
}

# --- Database Setup ---
db = SQLAlchemy(app)

class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('card.id'), nullable=True)
    parent = db.relationship('Card', back_populates='children', remote_side=[id])
    children = db.relationship('Card', back_populates='parent', cascade="all, delete-orphan")
    images = db.relationship('Image', back_populates='card', cascade="all, delete-orphan")

class Image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(100), nullable=False)
    card_id = db.Column(db.Integer, db.ForeignKey('card.id'), nullable=False)
    card = db.relationship('Card', back_populates='images')

# Ensure folders exist
instance_path = os.path.join(basedir, 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path)
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Create tables
with app.app_context():
    db.create_all()

# --- Helper Function ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Helper: Save file with unique name ---
def save_file(file):
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    counter = 1
    original_filename = filename
    while os.path.exists(filepath):
        name, ext = os.path.splitext(original_filename)
        filename = f"{name}_{counter}{ext}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        counter += 1
        
    file.save(filepath)
    return filename

# --- Public Portfolio Routes ---
# (home, projects, contact, experience routes remain the same)
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/projects')
def projects():
    return render_template('projects.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/experience')
def experience():
    return render_template("experience.html")

# --- Gallery Routes ---
# (gallery_login, gallery, gallery_logout routes remain the same)
@app.route('/gallery/login', methods=['GET', 'POST'])
def gallery_login():
    if request.method == 'POST':
        password = request.form.get('password')
        access_level = GALLERY_PASSWORDS.get(password)
        
        if access_level:
            session['gallery_access'] = access_level
            flash(f'Logged in with {access_level} access.', 'success')
            return redirect(url_for('gallery'))
        else:
            flash('Incorrect password.', 'error')
            
    return render_template('gallery_login.html')

@app.route('/gallery')
def gallery():
    access_level = session.get('gallery_access')
    if not access_level:
        return redirect(url_for('gallery_login'))
    top_level_cards = Card.query.filter_by(parent_id=None).all()
    return render_template('gallery.html', cards=top_level_cards, access_level=access_level)

@app.route('/gallery/logout')
def gallery_logout():
    session.pop('gallery_access', None)
    return redirect(url_for('home'))

# --- Admin-Only Routes ---

@app.route('/gallery/add_card', methods=['POST'])
def add_card():
    # (remains the same)
    if session.get('gallery_access') != 'admin':
        flash('You do not have permission to do that.', 'error')
        return redirect(url_for('gallery'))
        
    card_name = request.form.get('card_name')
    parent_id = request.form.get('parent_id')
    
    if card_name:
        parent_id = int(parent_id) if parent_id and parent_id != 'None' else None
        new_card = Card(name=card_name, parent_id=parent_id)
        db.session.add(new_card)
        db.session.commit()
        flash(f'Card "{card_name}" created.', 'success')
        
    return redirect(url_for('gallery'))

# --- NEW ROUTE: Edit Card Name ---
@app.route('/gallery/edit_card/<int:card_id>', methods=['POST'])
def edit_card(card_id):
    if session.get('gallery_access') != 'admin':
        flash('You do not have permission to do that.', 'error')
        return redirect(url_for('gallery'))

    card = Card.query.get_or_404(card_id)
    new_name = request.form.get('card_name')
    
    if new_name:
        card.name = new_name
        db.session.commit()
        flash(f'Card renamed to "{new_name}".', 'success')
    else:
        flash('New name cannot be empty.', 'error')
        
    return redirect(url_for('gallery'))

# --- UPDATED ROUTE: Upload Multiple Images ---
@app.route('/gallery/upload_image', methods=['POST'])
def upload_image():
    if session.get('gallery_access') != 'admin':
        flash('You do not have permission to do that.', 'error')
        return redirect(url_for('gallery'))

    card_id = request.form.get('card_id')
    # Use getlist to handle multiple files
    files = request.files.getlist('image') 

    card = Card.query.get(card_id)
    if not card:
        flash('Card not found.', 'error')
        return redirect(url_for('gallery'))

    uploaded_count = 0
    for file in files:
        if file and file.filename != '' and allowed_file(file.filename):
            # Use our helper to save the file
            filename = save_file(file)
            
            # Save to database
            new_image = Image(filename=filename, card_id=card.id)
            db.session.add(new_image)
            uploaded_count += 1
        else:
            if file and file.filename != '':
                flash(f'File "{file.filename}" is not an allowed type.', 'error')

    if uploaded_count > 0:
        db.session.commit()
        flash(f'{uploaded_count} image(s) uploaded successfully.', 'success')
    else:
        flash('No valid files were selected or uploaded.', 'error')

    return redirect(url_for('gallery'))

# --- NEW ROUTE: Upload Folder ---
@app.route('/gallery/upload_folder', methods=['POST'])
def upload_folder():
    if session.get('gallery_access') != 'admin':
        flash('You do not have permission to do that.', 'error')
        return redirect(url_for('gallery'))
        
    files = request.files.getlist('folder_files')
    
    if not files:
        flash('No folder or files selected.', 'error')
        return redirect(url_for('gallery'))

    # Logic: All files in the upload share a common base directory.
    # We'll use the first part of the path as the card name.
    # e.g., "My Trip/image1.jpg", "My Trip/image2.png"
    
    card_name = None
    new_card = None
    
    try:
        # Get the folder name from the first file
        first_file_path = files[0].filename
        # 'My Trip/image1.jpg' -> ['My Trip', 'image1.jpg']
        path_parts = first_file_path.split('/', 1)
        
        if len(path_parts) > 1:
            card_name = path_parts[0]
        else:
            # Fallback if it's just files, not in a folder
            card_name = "Uploaded Files"
            
        # Create the new card
        new_card = Card(name=card_name, parent_id=None) # Always create as top-level
        db.session.add(new_card)
        db.session.flush() # Get the new_card.id for images
        
        uploaded_count = 0
        for file in files:
            if file and allowed_file(file.filename):
                # Use helper to save file, it handles secure_filename
                filename = save_file(file)
                
                # Add image to the card we just created
                new_image = Image(filename=filename, card_id=new_card.id)
                db.session.add(new_image)
                uploaded_count += 1
        
        db.session.commit()
        flash(f'Folder "{card_name}" created with {uploaded_count} images.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'An error occurred during folder upload: {e}', 'error')

    return redirect(url_for('gallery'))


@app.route('/gallery/delete_card/<int:card_id>', methods=['POST'])
def delete_card(card_id):
    # (remains the same)
    if session.get('gallery_access') != 'admin':
        flash('You do not have permission to do that.', 'error')
        return redirect(url_for('gallery'))
        
    card_to_delete = Card.query.get_or_404(card_id)
    
    for image in card_to_delete.images:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], image.filename))
        except OSError:
            pass
            
    db.session.delete(card_to_delete)
    db.session.commit()
    flash(f'Card "{card_to_delete.name}" and all its contents deleted.', 'success')
    
    return redirect(url_for('gallery'))

@app.route('/gallery/delete_image/<int:image_id>', methods=['POST'])
def delete_image(image_id):
    # (remains the same)
    if session.get('gallery_access') != 'admin':
        flash('You do not have permission to do that.', 'error')
        return redirect(url_for('gallery'))

    image_to_delete = Image.query.get_or_404(image_id)
    
    try:
        os.remove(os.path.join(app.config['UPLOAD_FOLDER'], image_to_delete.filename))
    except OSError:
        pass
        
    db.session.delete(image_to_delete)
    db.session.commit()
    
    flash('Image deleted.', 'success')
    
    return redirect(url_for('gallery'))


if __name__ == '__main__':
    app.run(debug=True)