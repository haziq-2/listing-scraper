"""Craigslist worldwide site-list parsing."""

from services.craigslist_sites import parse_sites_html


def test_parse_area_links_not_www_subdomain():
    html = """
    <section class="body">
      <h1>US</h1>
      <h4>Texas</h4>
      <a href="https://www.craigslist.org/area/dallas">dallas / fort worth</a>
      <a href="https://www.craigslist.org/area/austin">austin</a>
      <a href="https://austin.craigslist.org/">legacy austin</a>
    </section>
    """
    sites = parse_sites_html(html)
    by_slug = {site.subdomain: site for site in sites}
    assert "www" not in by_slug
    assert by_slug["dallas"].name == "dallas / fort worth"
    assert by_slug["dallas"].url == "https://www.craigslist.org/area/dallas"
    assert by_slug["austin"].name == "austin"
    assert by_slug["dallas"].subsection == "Texas"
