import sys
import asyncio
import subprocess
from typing import List, Dict
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QHBoxLayout, QLineEdit, QPushButton, QListWidget,
                            QListWidgetItem, QStackedWidget, QProgressBar,
                            QLabel, QScrollArea)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QPixmap, QImage
import qasync
import innertube
import requests
from io import BytesIO

class VideoItemWidget(QWidget):
    def __init__(self, title: str, author: str, views: str, publish_date: str, thumbnail_url: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Thumbnail
        thumbnail_label = QLabel()
        thumbnail_label.setFixedSize(160, 90)
        thumbnail_label.setScaledContents(True)
        thumbnail_label.setStyleSheet("background-color: #f0f0f0;")
        
        # Load thumbnail
        try:
            response = requests.get(thumbnail_url)
            image = QImage()
            image.loadFromData(response.content)
            pixmap = QPixmap.fromImage(image)
            thumbnail_label.setPixmap(pixmap)
        except:
            thumbnail_label.setText("No preview")
        
        layout.addWidget(thumbnail_label)
        
        # Video info
        info_layout = QVBoxLayout()
        
        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold;")
        title_label.setTextFormat(Qt.TextFormat.PlainText)
        title_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        title_label.setToolTip(title)  # Show full title on hover
        info_layout.addWidget(title_label)
        
        # Author
        author_label = QLabel(author)
        author_label.setStyleSheet("color: #606060;")
        info_layout.addWidget(author_label)
        
        # Views and date
        views_date_label = QLabel(f"{views} • {publish_date}")
        views_date_label.setStyleSheet("color: #606060;")
        info_layout.addWidget(views_date_label)
        
        layout.addLayout(info_layout)
        layout.addStretch()

class YouTubeSearchApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube Search")
        self.setMinimumSize(800, 600)
        
        # Initialize the innertube client
        self.client = innertube.InnerTube("WEB")
        
        # Create stacked widget for pages
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)
        
        # Create main page
        self.main_page = QWidget()
        main_layout = QVBoxLayout(self.main_page)
        
        # Create search input and button
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter search query...")
        self.search_input.returnPressed.connect(self.start_search)
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self.start_search)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.search_button)
        main_layout.addLayout(search_layout)
        
        # Create results list
        self.results_list = QListWidget()
        self.results_list.setSpacing(5)
        self.results_list.itemDoubleClicked.connect(self.open_video)
        main_layout.addWidget(self.results_list)
        
        # Create loading page
        self.loading_page = QWidget()
        loading_layout = QVBoxLayout(self.loading_page)
        
        # Add loading spinner
        self.loading_spinner = QProgressBar()
        self.loading_spinner.setRange(0, 0)
        self.loading_spinner.setTextVisible(False)
        self.loading_spinner.setFixedHeight(4)
        loading_layout.addWidget(self.loading_spinner)
        
        # Add loading text
        loading_label = QLabel("Searching...")
        loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        loading_layout.addWidget(loading_label)
        
        # Add pages to stacked widget
        self.stacked_widget.addWidget(self.main_page)
        self.stacked_widget.addWidget(self.loading_page)
        
        # Store video data
        self.video_data: List[Dict] = []
        
        # Initialize mpv process and timer
        self.mpv_process = None
        self.mpv_check_timer = QTimer()
        self.mpv_check_timer.timeout.connect(self.check_mpv_status)
        self.mpv_check_timer.start(1000)

    def format_views(self, views: int) -> str:
        """Format view count to a readable string"""
        if views >= 1000000:
            return f"{views/1000000:.1f}M views"
        elif views >= 1000:
            return f"{views/1000:.1f}K views"
        return f"{views} views"

    def format_date(self, date_str: str) -> str:
        """Format publish date to a readable string"""
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d")
            return date.strftime("%b %d, %Y")
        except:
            return date_str

    def show_loading(self):
        """Show loading page"""
        self.stacked_widget.setCurrentWidget(self.loading_page)
        self.search_button.setEnabled(False)
        self.search_input.setEnabled(False)

    def show_main(self):
        """Show main page"""
        self.stacked_widget.setCurrentWidget(self.main_page)
        self.search_button.setEnabled(True)
        self.search_input.setEnabled(True)

    def check_mpv_status(self):
        """Check if mpv is still running and show window if it's not"""
        if self.mpv_process is not None:
            if self.mpv_process.poll() is not None:
                self.mpv_process = None
                self.show()
                self.activateWindow()

    async def perform_search(self, query: str):
        """Perform async YouTube search using innertube"""
        try:
            self.results_list.clear()
            self.video_data.clear()
            
            data = await asyncio.to_thread(self.client.search, query=query)
            
            if 'contents' in data and 'twoColumnSearchResultsRenderer' in data['contents']:
                results = data['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents'][0]['itemSectionRenderer']['contents']
                
                for item in results:
                    if 'videoRenderer' in item:
                        video = item['videoRenderer']
                        title = video['title']['runs'][0]['text']
                        author = video['ownerText']['runs'][0]['text']
                        video_id = video['videoId']
                        
                        # Parse view count
                        views = 0
                        view_text = video.get('viewCountText', {}).get('simpleText', '0')
                        if view_text:
                            # Remove commas and non-numeric characters
                            view_text = ''.join(c for c in view_text if c.isdigit())
                            if view_text:
                                views = int(view_text)
                        
                        publish_date = video.get('publishedTimeText', {}).get('simpleText', 'Unknown date')
                        thumbnail_url = video['thumbnail']['thumbnails'][-1]['url']
                        
                        self.video_data.append({
                            'title': title,
                            'author': author,
                            'video_id': video_id,
                            'views': views,
                            'publish_date': publish_date,
                            'thumbnail_url': thumbnail_url
                        })
                        
                        # Create custom widget for the video item
                        video_widget = VideoItemWidget(
                            title=title,
                            author=author,
                            views=self.format_views(views),
                            publish_date=self.format_date(publish_date),
                            thumbnail_url=thumbnail_url
                        )
                        
                        # Create list item and set its size
                        list_item = QListWidgetItem()
                        list_item.setSizeHint(video_widget.sizeHint())
                        
                        # Add widget to list
                        self.results_list.addItem(list_item)
                        self.results_list.setItemWidget(list_item, video_widget)
        
        except Exception as e:
            self.results_list.addItem(f"Error: {str(e)}")
        finally:
            self.show_main()

    def start_search(self):
        """Start the async search process"""
        query = self.search_input.text().strip()
        if query:
            self.show_loading()
            asyncio.create_task(self.perform_search(query))

    def open_video(self, item: QListWidgetItem):
        """Open video in mpv when double-clicked"""
        index = self.results_list.row(item)
        if 0 <= index < len(self.video_data):
            video_id = self.video_data[index]['video_id']
            url = f"https://www.youtube.com/watch?v={video_id}"
            try:
                self.mpv_process = subprocess.Popen(['mpv', url])
                self.hide()
            except Exception as e:
                self.results_list.addItem(f"Error opening mpv: {str(e)}")

async def main():
    """Main async function to run the application"""
    app = QApplication(sys.argv)
    window = YouTubeSearchApp()
    window.show()
    
    await qasync.QEventLoop(app).run_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
