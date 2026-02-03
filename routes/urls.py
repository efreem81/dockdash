"""
URL Sharing Routes
Shared bookmark management
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from models import SharedURL
from config import db

urls_bp = Blueprint('urls', __name__)


@urls_bp.route('/urls')
@login_required
def url_list():
    category = request.args.get('category', None)
    if category:
        urls = SharedURL.query.filter_by(category=category).order_by(SharedURL.created_at.desc()).all()
    else:
        urls = SharedURL.query.order_by(SharedURL.created_at.desc()).all()
    
    categories = db.session.query(SharedURL.category).distinct().all()
    categories = [c[0] for c in categories]
    
    return render_template('urls.html', urls=urls, categories=categories, current_category=category)


@urls_bp.route('/urls/add', methods=['GET', 'POST'])
@login_required
def add_url():
    if request.method == 'POST':
        title = request.form.get('title')
        url = request.form.get('url')
        description = request.form.get('description')
        category = request.form.get('category') or 'General'
        
        if not title or not url:
            flash('Title and URL are required', 'error')
        else:
            shared_url = SharedURL(
                title=title,
                url=url,
                description=description,
                category=category,
                created_by=current_user.id
            )
            db.session.add(shared_url)
            db.session.commit()
            flash('URL added successfully!', 'success')
            return redirect(url_for('urls.url_list'))
    
    categories = db.session.query(SharedURL.category).distinct().all()
    categories = [c[0] for c in categories]
    
    return render_template('add_url.html', categories=categories)


@urls_bp.route('/urls/<int:url_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_url(url_id):
    shared_url = SharedURL.query.get_or_404(url_id)
    
    if request.method == 'POST':
        shared_url.title = request.form.get('title')
        shared_url.url = request.form.get('url')
        shared_url.description = request.form.get('description')
        shared_url.category = request.form.get('category') or 'General'
        
        if not shared_url.title or not shared_url.url:
            flash('Title and URL are required', 'error')
        else:
            db.session.commit()
            flash('URL updated successfully!', 'success')
            return redirect(url_for('urls.url_list'))
    
    categories = db.session.query(SharedURL.category).distinct().all()
    categories = [c[0] for c in categories]
    
    return render_template('edit_url.html', shared_url=shared_url, categories=categories)


@urls_bp.route('/urls/<int:url_id>/delete', methods=['POST'])
@login_required
def delete_url(url_id):
    shared_url = SharedURL.query.get_or_404(url_id)
    db.session.delete(shared_url)
    db.session.commit()
    flash('URL deleted successfully!', 'success')
    return redirect(url_for('urls.url_list'))


@urls_bp.route('/api/urls')
@login_required
def api_urls():
    urls = SharedURL.query.order_by(SharedURL.created_at.desc()).all()
    return jsonify([{
        'id': u.id,
        'title': u.title,
        'url': u.url,
        'description': u.description,
        'category': u.category,
        'created_at': u.created_at.isoformat()
    } for u in urls])
