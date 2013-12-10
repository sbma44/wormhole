import web

urls = (
    '/', 'status',
    '/aws', 'aws',
    '/location', 'location',
    '/launch', 'launch',
    '/about', 'about'
)

class status:
    def GET(self):
    	web.header('Content-Type', 'text/html')
    	render = web.template.render('html')
    	return render.status()

if __name__ == "__main__":
    app = web.application(urls, globals())
    app.run()