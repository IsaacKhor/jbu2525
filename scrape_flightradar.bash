for airport in $(cat airports.txt); do
    echo "Fetching schedule for $airport"
    curl 'https://www.flightradar24.com/data/airlines/b6-jbu/routes?get-airport-arr-dep='$airport \
            --compressed -s \
            -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:140.0) Gecko/20100101 Firefox/140.0' \
            -H 'Accept: */*' \
            -H 'Accept-Language: en-US,en;q=0.5' \
            -H 'Accept-Encoding: gzip, deflate, br, zstd' \
            -H 'Referer: https://www.flightradar24.com/data/airlines/b6-jbu/routes' \
            -H 'Content-Type: application/json' \
            -H 'X-Fetch: true' \
            -H 'Alt-Used: www.flightradar24.com' \
            -H 'Sec-Fetch-Dest: empty' \
            -H 'Sec-Fetch-Mode: cors' \
            -H 'Sec-Fetch-Site: same-origin' \
            -H 'Priority: u=0' > schedule/$airport.json
    sleep 10
done