from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import instaloader
import os
import tempfile
app = Flask(__name__)
CORS(app)
@app.route('/download', methods=['POST'])
def download_video():
    try:
        url = request.json.get('url')
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        # Extract post shortcode from URL
        shortcode = url.split('/')[-2]
        # Create a temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Initialize Instaloader
            L = instaloader.Instaloader(dirname_pattern=temp_dir)
            
            # Download the post
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            L.download_post(post, target=temp_dir)
            # Find the video file
            video_file = None
            for file in os.listdir(temp_dir):
                if file.endswith('.mp4'):
                    video_file = os.path.join(temp_dir, file)
                    break
            if not video_file:
                return jsonify({'error': 'No video found'}), 404
            return send_file(video_file, as_attachment=True)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
