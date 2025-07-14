for airport in $(cat airports.txt); do
    curl "https://www.flightconnections.com/airports_url.php?lang=en^&iata=${airport}" \
        -H 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:140.0) Gecko/20100101 Firefox/140.0' \
        -H 'Accept: */*' \
        -H 'Accept-Language: en-US,en;q=0.5' \
        -H 'Accept-Encoding: gzip, deflate, br, zstd' \
        -H 'X-Requested-With: XMLHttpRequest' \
        -H 'Connection: keep-alive' \
        -H 'Sec-Fetch-Dest: empty' \
        -H 'Sec-Fetch-Mode: cors' \
        -H 'Sec-Fetch-Site: same-origin' \
        -H 'TE: trailers' -s | tee -a airports_ids.txt
    echo '' | tee -a airports_ids.txt
    sleep 5
done