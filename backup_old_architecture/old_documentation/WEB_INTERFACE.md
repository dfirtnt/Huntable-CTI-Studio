# 🌐 CTI Scraper Web Interface

A modern, responsive web interface for the CTI Scraper threat intelligence platform, built with FastAPI and modern web technologies.

## ✨ Features

### 🏠 **Dashboard**
- Real-time overview of collected threat intelligence
- Statistics cards showing total articles, sources, and database size
- Recent articles with quick access
- Source status monitoring
- Auto-refresh every 30 seconds

### 📰 **Articles Browser**
- Browse all collected threat intelligence articles
- Advanced filtering by source, search terms, and quality score
- Pagination for large collections
- Quick access to article details and original sources

### 🔍 **TTP Analysis Dashboard**
- Comprehensive threat hunting technique analysis
- Quality assessment metrics and visualizations
- Technique breakdown by category
- Interactive charts using Chart.js
- Top articles ranked by hunting value

### 📊 **Article Details**
- Full article content with TTP analysis
- Quality assessment with detailed scoring
- Huntable techniques with confidence scores
- Hunting guidance for each detected technique
- Quality factor breakdown

### ⚙️ **Source Management**
- View all configured threat intelligence sources
- Source status and health monitoring
- Collection method indicators (RSS vs Web Scraping)
- Tier classification and statistics

## 🚀 Quick Start

### 1. **Start the Web Server**
```bash
# Using the startup script
./start_web.sh

# Or manually
source venv/bin/activate
python src/web/main.py
```

### 2. **Access the Interface**
Open your browser and navigate to:
```
http://localhost:8000
```

### 3. **Navigate the Interface**
- **Dashboard**: Overview and quick actions
- **Articles**: Browse and search collected intelligence
- **TTP Analysis**: View hunting techniques and quality metrics
- **Sources**: Manage threat intelligence sources

## 🛠️ Technology Stack

### **Backend**
- **FastAPI**: Modern, fast web framework
- **SQLAlchemy**: Database ORM and management
- **Jinja2**: Template engine for HTML generation

### **Frontend**
- **Tailwind CSS**: Utility-first CSS framework
- **HTMX**: Dynamic interactions without JavaScript complexity
- **Chart.js**: Interactive data visualizations

### **Features**
- **Responsive Design**: Works on desktop, tablet, and mobile
- **Real-time Updates**: Auto-refresh and dynamic content loading
- **Search & Filtering**: Advanced article discovery
- **Quality Assessment**: TTP quality scoring and visualization

## 📱 Responsive Design

The web interface is fully responsive and works on:
- **Desktop**: Full-featured dashboard with sidebars
- **Tablet**: Optimized layout for medium screens
- **Mobile**: Touch-friendly interface with collapsible navigation

## 🔧 Configuration

### **Port Configuration**
The web server runs on port 8000 by default. To change this:

```python
# In src/web/main.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)  # Change port here
```

### **Database Connection**
The web interface automatically uses the same database configuration as the CLI:

```python
# Uses the default SQLite database
db_manager = DatabaseManager()
```

## 📊 API Endpoints

### **HTML Endpoints**
- `GET /` - Main dashboard
- `GET /articles` - Articles browser with filtering
- `GET /articles/{id}` - Article details with TTP analysis
- `GET /analysis` - TTP analysis dashboard
- `GET /sources` - Source management

### **JSON API Endpoints**
- `GET /api/articles` - Articles data (JSON)
- `GET /api/analysis/{id}` - Article TTP analysis (JSON)

## 🎨 Customization

### **Styling**
- Modify `src/web/templates/base.html` for global styles
- Update individual template files for page-specific styling
- Customize Tailwind CSS classes for consistent design

### **Templates**
- All templates use Jinja2 syntax
- Extend `base.html` for consistent layout
- Use Tailwind CSS classes for styling

### **JavaScript**
- Add custom JavaScript in template `{% block scripts %}`
- Use HTMX for dynamic interactions
- Chart.js for data visualizations

## 🔒 Security Considerations

### **Current Implementation**
- No authentication (development mode)
- CORS enabled for all origins
- Direct database access

### **Production Recommendations**
- Add authentication and authorization
- Implement rate limiting
- Use HTTPS in production
- Add input validation and sanitization
- Consider API key authentication for external access

## 🚨 Troubleshooting

### **Common Issues**

#### **Port Already in Use**
```bash
# Kill processes using port 8000
lsof -ti:8000 | xargs kill -9
```

#### **Import Errors**
```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Check import paths in src/web/main.py
```

#### **Database Connection Issues**
```bash
# Verify database exists and is accessible
ls -la threat_intel.db

# Check database permissions
```

#### **Template Errors**
```bash
# Verify template files exist
ls -la src/web/templates/

# Check Jinja2 syntax in templates
```

### **Debug Mode**
To run with debug information:

```python
# In src/web/main.py
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True, log_level="debug")
```

## 🔄 Integration with CLI

The web interface works alongside the existing CLI:

```bash
# Collect threat intelligence
./threat-intel.sh collect

# View in web interface
./start_web.sh

# Access at http://localhost:8000
```

## 📈 Performance

### **Optimizations**
- Database connection pooling
- Efficient SQL queries with proper indexing
- Lazy loading of article content
- Pagination for large datasets
- Background processing for TTP analysis

### **Scaling Considerations**
- For large datasets, consider implementing caching
- Use background tasks for heavy operations
- Implement database read replicas for high traffic
- Consider CDN for static assets

## 🎯 Future Enhancements

### **Planned Features**
- User authentication and role-based access
- Real-time notifications for new articles
- Advanced search with full-text indexing
- Export functionality (PDF, CSV, JSON)
- Integration with SIEM platforms
- Automated threat intelligence sharing

### **API Extensions**
- RESTful API for external integrations
- Webhook support for real-time updates
- GraphQL endpoint for complex queries
- Bulk operations for large datasets

## 📚 Additional Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Tailwind CSS Documentation](https://tailwindcss.com/docs)
- [HTMX Documentation](https://htmx.org/docs/)
- [Chart.js Documentation](https://www.chartjs.org/docs/)

---

**🎉 The CTI Scraper now has a beautiful, modern web interface for threat intelligence analysis!**
