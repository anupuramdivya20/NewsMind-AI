from newspaper import Article

def get_full_article(url):

    try:

        article = Article(url)

        article.download()

        article.parse()

        return {

            "title": article.title,

            "text": article.text,

            "image": article.top_image,

            "authors": article.authors,

            "publish_date": article.publish_date

        }

    except Exception as e:

        print(e)

        return None